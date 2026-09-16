"""CRM-owned phone verification for the acting user's own profile (D-155-D-157).

Not a Keycloak/OIDC change (D-002 stays intact): the verified phone lives only in this CRM's own
database (models.py: User.phone/phone_verified_at, PhoneVerificationCode). The code-send step runs
synchronously in the request handler (D-156), and no real SMS gateway is integrated (D-157,
app/sms.py) — in local dev/CI the code is only visible in the API container's log.
"""
import secrets
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import PhoneVerificationCode, utcnow
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


class PhoneRequestInput(BaseModel):
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class PhoneRequestResponse(BaseModel):
    expires_in: int


class PhoneVerifyInput(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]


class PhoneVerifyResponse(BaseModel):
    phone: str
    phone_verified_at: datetime | None


def _generate_code() -> str:
    # secrets.randbelow (not `random`): verification codes must not be guessable from a seeded PRNG.
    return f'{secrets.randbelow(1_000_000):06d}'


def _hash_code(code: str) -> str:
    return token_hash(code)


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
