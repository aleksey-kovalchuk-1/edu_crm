"""The acting user's own profile (Настройки → Личный профиль; spec 2026-09-27, section 1) and the
CRM-owned phone verification for it (D-155-D-157).

Names live in Keycloak (firstName/lastName/attributes.middleName) and are mirrored here; time zone and
the Telegram/WhatsApp contacts are CRM-only saved values with no messaging integration. The phone is
changed only by the SMS verification below, never by PATCH /profile.

Not a Keycloak/OIDC change (D-002 stays intact): the verified phone lives only in this CRM's own
database (models.py: User.phone/phone_verified_at, PhoneVerificationCode). The code-send step runs
synchronously in the request handler (D-156), and no real SMS gateway is integrated (D-157,
app/sms.py) — in local dev/CI the code is only visible in the API container's log.
"""
import re
import secrets
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .keycloak_admin import KeycloakAdminError
from .models import PhoneVerificationCode, User, utcnow
from .owner_links import normalize_name, normalized_column, rename_user
from .phone import PhoneFormatError, mask_phone, normalize_phone
from .security import token_hash, tokens_match
from .sms import SmsSendError, send_sms

router = APIRouter(prefix='/api/v1/profile', tags=['Профиль'])
any_role = require_roles(*ALL_ROLES)

CODE_TTL_MINUTES = 5
COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5

CODE_UNAVAILABLE_MESSAGE = 'Код недействителен или устарел, запросите новый'
WRONG_CODE_MESSAGE = 'Неверный код, попробуйте ещё раз'
LOCKED_MESSAGE = 'Слишком много неверных попыток, запросите новый код'
COOLDOWN_MESSAGE = 'Код уже отправлен, следующий можно запросить не раньше чем через минуту'
SEND_FAILED_MESSAGE = 'Не удалось отправить SMS, попробуйте ещё раз позже'
MOBILE_MESSAGE = 'Укажите мобильный номер в формате +7 9XX XXX-XX-XX'
NAME_TAKEN_MESSAGE = 'Такое имя уже есть у другого пользователя CRM'
KEYCLOAK_DOWN_MESSAGE = 'Не удалось сохранить имя: сервис учётных записей недоступен, попробуйте позже'
TELEGRAM_RE = re.compile(r'^[A-Za-z0-9_]{5,32}$')


class PhoneRequestInput(BaseModel):
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class PhoneRequestResponse(BaseModel):
    expires_in: int


class PhoneVerifyInput(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]


class PhoneVerifyResponse(BaseModel):
    phone: str
    phone_verified_at: datetime | None


def _field_error(field, message):
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': field, 'message': message, 'type': 'value_error'}])


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProfilePatch(BaseModel):
    # extra='forbid': the phone (or anything else) must never be settable through this endpoint.
    model_config = ConfigDict(extra='forbid')
    first_name: Name | None = None
    middle_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    last_name: Name | None = None
    timezone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    telegram: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    whatsapp: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None


class ProfileOut(BaseModel):
    id: int
    email: str
    first_name: str
    middle_name: str
    last_name: str
    full_name: str
    phone: str
    phone_verified_at: datetime | None
    timezone: str
    telegram: str
    whatsapp: str
    email_sender_identity_id: int | None


def _names_of(user):
    first, last = user.first_name, user.last_name
    if not first and not last:
        first, _, last = user.full_name.partition(' ')
    return first, last


def profile_out(user):
    first, last = _names_of(user)
    return ProfileOut(
        id=user.id, email=user.email, first_name=first, middle_name=user.middle_name, last_name=last,
        full_name=user.full_name, phone=user.phone, phone_verified_at=user.phone_verified_at,
        timezone=user.timezone, telegram=user.telegram, whatsapp=user.whatsapp,
        email_sender_identity_id=user.email_sender_identity_id,
    )


def _clean_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise _field_error('timezone', 'Выберите часовой пояс из списка')
    return value


def _clean_telegram(value):
    value = value.removeprefix('@')
    if value and not TELEGRAM_RE.match(value):
        raise _field_error('telegram', 'Имя пользователя Telegram: 5–32 символа, латинские буквы, цифры и «_»')
    return value


def _clean_whatsapp(value):
    if not value:
        return ''
    try:
        return normalize_phone(value)
    except PhoneFormatError:
        raise _field_error('whatsapp', 'Номер WhatsApp в формате +7XXXXXXXXXX')


@router.get('', response_model=ProfileOut, summary='Мой профиль')
def get_profile(auth: AuthContext = Depends(any_role)):
    return profile_out(auth.user)


@router.patch('', response_model=ProfileOut, summary='Изменить мой профиль')
def update_profile(data: ProfilePatch, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    user = auth.user
    timezone = _clean_timezone(data.timezone) if data.timezone is not None else None
    telegram = _clean_telegram(data.telegram) if data.telegram is not None else None
    whatsapp = _clean_whatsapp(data.whatsapp) if data.whatsapp is not None else None

    changed = []
    current_first, current_last = _names_of(user)
    first = data.first_name if data.first_name is not None else current_first
    last = data.last_name if data.last_name is not None else current_last
    middle = data.middle_name if data.middle_name is not None else user.middle_name
    full_name = f'{first} {last}'.strip()
    name_changed = full_name != user.full_name
    names_changed = name_changed or (first, last, middle) != (current_first, current_last, user.middle_name)
    if names_changed and name_changed:
        taken = db.scalar(select(User.id).where(
            User.id != user.id, User.is_active.is_(True), normalized_column(User.full_name) == normalize_name(full_name),
        ).limit(1))
        if taken is not None:
            raise _field_error('first_name', NAME_TAKEN_MESSAGE)
    if names_changed:
        keycloak_admin = request.app.state.keycloak_admin
        if not keycloak_admin.is_configured():
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, KEYCLOAK_DOWN_MESSAGE)
        try:
            keycloak_admin.update_user_names(user.keycloak_sub, first_name=first, last_name=last, middle_name=middle)
        except KeycloakAdminError as error:
            db.rollback()
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, KEYCLOAK_DOWN_MESSAGE) from error
        rename_user(db, request, user, first_name=first, last_name=last, full_name=full_name)
        user.middle_name = middle
        changed.append('name')

    for field, value in (('timezone', timezone), ('telegram', telegram), ('whatsapp', whatsapp)):
        if value is not None and value != getattr(user, field):
            setattr(user, field, value)
            changed.append(field)
    if changed:
        # Field names only: contact values stay out of the audit log.
        record_event(db, request, user, 'profile.update', entity_type='user', entity_id=user.id,
                     summary='Изменён личный профиль', payload={'fields': changed})
    db.commit()
    return profile_out(user)


def _generate_code() -> str:
    # secrets.randbelow (not `random`): verification codes must not be guessable from a seeded PRNG.
    return f'{secrets.randbelow(1_000_000):06d}'


def _hash_code(code: str) -> str:
    return token_hash(code)


def _lock_phone_requests_for_user(db: Session, user_id: int) -> None:
    """Serializes concurrent /profile/phone requests for one user (transaction-scoped Postgres advisory
    lock; released automatically on commit/rollback, no new table or migration needed).

    Without this, two near-simultaneous requests (a double click, a retried request) can both pass the
    cooldown check before either has inserted its row, and both end up sending an SMS. The lock forces
    the second request to wait for the first's transaction to finish, so by the time it re-reads the
    cooldown it sees the first request's row and is correctly rejected.
    """
    # hashtext(...) keys the lock to this feature specifically, so it can never collide with an
    # unrelated advisory lock some other feature might use with a raw id as the key.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('phone_verification_request:' || :user_id))"), {'user_id': user_id})


def _sms_sender(request: Request):
    # app.state.sms_sender is set by create_app (defaulting to sms.send_sms); tests override it with
    # a fake so they can assert what would have been sent without hitting real HTTP or reading logs.
    return getattr(request.app.state, 'sms_sender', send_sms)


@router.post(
    '/phone', status_code=202, response_model=PhoneRequestResponse,
    summary='Запросить код подтверждения номера телефона',
)
def request_phone_code(
    data: PhoneRequestInput, request: Request,
    auth: AuthContext = Depends(any_role), db: Session = Depends(get_db),
):
    try:
        phone = normalize_phone(data.phone)
    except PhoneFormatError as error:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            details=[{'field': 'phone', 'message': str(error), 'type': 'value_error'}],
        ) from error
    if not phone.startswith('+79'):
        raise _field_error('phone', MOBILE_MESSAGE)

    # Held for the rest of this transaction (through the cooldown check, the SMS send, and the insert
    # below): a second concurrent request for the same user blocks here until this one commits or
    # rolls back, so it always sees an up-to-date cooldown instead of racing this one to the insert.
    _lock_phone_requests_for_user(db, auth.user.id)

    now = utcnow()
    last = db.scalar(
        select(PhoneVerificationCode)
        .where(PhoneVerificationCode.user_id == auth.user.id)
        .order_by(PhoneVerificationCode.created_at.desc())
        .limit(1)
    )
    if last is not None and (now - last.created_at).total_seconds() < COOLDOWN_SECONDS:
        raise AppError(ErrorCode.RATE_LIMITED, COOLDOWN_MESSAGE)

    code = _generate_code()
    message = f'Код подтверждения телефона: {code}. Никому не сообщайте его.'
    try:
        _sms_sender(request)(request.app.state.settings, phone, message)
    except SmsSendError:
        # No row is created: a code that was never actually sent must not block an immediate retry.
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, SEND_FAILED_MESSAGE)

    db.add(PhoneVerificationCode(
        user_id=auth.user.id,
        phone=phone,
        code_hash=_hash_code(code),
        correlation_id=getattr(request.state, 'correlation_id', None),
        created_at=now,
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    ))
    record_event(
        db, request, auth.user, 'phone.verification_requested',
        entity_type='user', entity_id=auth.user.id,
        summary=f'Запрошен код подтверждения телефона {mask_phone(phone)}',
        payload={'phone_masked': mask_phone(phone)},
    )
    db.commit()
    return PhoneRequestResponse(expires_in=CODE_TTL_MINUTES * 60)


@router.post(
    '/phone/verify', response_model=PhoneVerifyResponse,
    summary='Подтвердить номер телефона кодом из SMS',
)
def verify_phone_code(
    data: PhoneVerifyInput, request: Request,
    auth: AuthContext = Depends(any_role), db: Session = Depends(get_db),
):
    now = utcnow()
    record = db.scalar(
        select(PhoneVerificationCode)
        .where(
            PhoneVerificationCode.user_id == auth.user.id,
            PhoneVerificationCode.consumed_at.is_(None),
            PhoneVerificationCode.expires_at > now,
        )
        .order_by(PhoneVerificationCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    # A record already at the attempt limit is treated the same as "nothing to verify": the
    # lockout is permanent even if the code just submitted happens to be correct.
    if record is None or record.attempts >= MAX_ATTEMPTS:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, CODE_UNAVAILABLE_MESSAGE)

    if not tokens_match(record.code_hash, _hash_code(data.code)):
        record.attempts += 1
        just_locked = record.attempts >= MAX_ATTEMPTS
        db.commit()
        if just_locked:
            raise AppError(ErrorCode.CONFLICT, LOCKED_MESSAGE)
        raise AppError(
            ErrorCode.VALIDATION_ERROR, WRONG_CODE_MESSAGE,
            details=[{'field': 'code', 'message': WRONG_CODE_MESSAGE, 'type': 'value_error'}],
        )

    record.consumed_at = now
    auth.user.phone = record.phone
    auth.user.phone_verified_at = now
    record_event(
        db, request, auth.user, 'phone.verified',
        entity_type='user', entity_id=auth.user.id,
        summary=f'Телефон {mask_phone(record.phone)} подтверждён',
        payload={'phone_masked': mask_phone(record.phone)},
    )
    db.commit()
    return PhoneVerifyResponse(phone=auth.user.phone, phone_verified_at=auth.user.phone_verified_at)
