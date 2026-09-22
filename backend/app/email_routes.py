"""Sender-identity catalog for outgoing university correspondence (Настройки → Личный профиль).
Every identity is admin-created and therefore inherently approved — see EmailSenderIdentity's
docstring in models.py for why there is no separate self-service verification flow.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .db import get_db
from .email import EmailSendError, send_email
from .errors import AppError, ErrorCode
from .models import EmailSenderIdentity, utcnow

router = APIRouter(prefix='/api/v1/email-senders', tags=['Отправители писем'])
any_role = require_roles(*ALL_ROLES)
sender_manager = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TEST_SEND_COOLDOWN_SECONDS = 60
TEST_SEND_COOLDOWN_MESSAGE = 'Тестовое письмо уже отправлено, следующее можно запросить не раньше чем через минуту'


class SenderIn(BaseModel):
    email_address: EmailStr
    display_name: DisplayName


class SenderOut(BaseModel):
    id: int
    email_address: str
    display_name: str
    is_active: bool


def sender_out(row):
    return SenderOut(id=row.id, email_address=row.email_address, display_name=row.display_name, is_active=row.is_active)


@router.get('', response_model=list[SenderOut], summary='Список доступных отправителей', dependencies=[Depends(any_role)])
def list_senders(db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailSenderIdentity).where(EmailSenderIdentity.is_active.is_(True)).order_by(EmailSenderIdentity.display_name)).all()
    return [sender_out(r) for r in rows]


@router.post('', response_model=SenderOut, status_code=201, summary='Добавить отправителя')
def create_sender(data: SenderIn, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    existing = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.email_address == data.email_address))
    if existing is not None and existing.is_active:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'email_address', 'message': 'Такой адрес уже добавлен', 'type': 'value_error'}])
    if existing is not None:
        existing.is_active = True
        existing.display_name = data.display_name
        existing.created_by_user_id = auth.user.id
        record_event(db, request, auth.user, 'email_sender.reactivate', entity_type='email_sender_identity', entity_id=existing.id,
                     summary=f'Восстановлен отправитель писем «{existing.display_name}» ({existing.email_address})', payload={'email_address': existing.email_address})
        db.commit()
        return sender_out(existing)
    row = EmailSenderIdentity(email_address=data.email_address, display_name=data.display_name, created_by_user_id=auth.user.id)
    db.add(row)
    db.flush()
    record_event(db, request, auth.user, 'email_sender.create', entity_type='email_sender_identity', entity_id=row.id,
                 summary=f'Добавлен отправитель писем «{row.display_name}» ({row.email_address})', payload={'email_address': row.email_address})
    db.commit()
    return sender_out(row)


@router.delete('/{sender_id}', status_code=204, summary='Деактивировать отправителя')
def deactivate_sender(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = db.get(EmailSenderIdentity, sender_id)
    if row is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    row.is_active = False
    record_event(db, request, auth.user, 'email_sender.deactivate', entity_type='email_sender_identity', entity_id=row.id,
                 summary=f'Деактивирован отправитель писем «{row.display_name}» ({row.email_address})', payload={})
    db.commit()


class TestSendOut(BaseModel):
    delivered: bool
    message: str


@router.post('/test', response_model=TestSendOut, summary='Отправить тестовое письмо на свой адрес')
def test_send(request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    if not auth.user.email:
        raise AppError(ErrorCode.CONFLICT, 'В вашем профиле не указан email — отправить тестовое письмо некуда')
    settings = request.app.state.settings
    # Defaults to the real settings-driven sender (see app/email.py); tests substitute a fake here,
    # same pattern as app.state.sms_sender.
    sender = getattr(request.app.state, 'email_sender', None) or send_email
    # "Configured" means real delivery is actually possible: either the settings-driven default
    # sender has a provider URL to call (the same condition send_email itself checks before falling
    # back to logging), or the request-scoped sender has been swapped for something other than that
    # default — which is how tests stand in for "a working provider is in place" without touching
    # settings.email_provider_url or hitting real HTTP.
    configured = bool(settings.email_provider_url) or sender is not send_email
    from_identity = db.get(EmailSenderIdentity, auth.user.email_sender_identity_id) if auth.user.email_sender_identity_id else None
    from_label = from_identity.email_address if from_identity else (settings.email_sender_address or settings.email_sender_name)
    from_address = from_identity.email_address if from_identity else (settings.email_sender_address or None)
    subject = 'Тестовое письмо UniCRM'
    body = f'Это тестовое письмо, отправленное от имени «{from_label}». Если вы получили его, отправка почты настроена верно.'
    now = utcnow()
    if auth.user.email_test_sent_at is not None and (now - auth.user.email_test_sent_at).total_seconds() < TEST_SEND_COOLDOWN_SECONDS:
        raise AppError(ErrorCode.RATE_LIMITED, TEST_SEND_COOLDOWN_MESSAGE)
    try:
        # Always the caller's own Keycloak-sourced address — never a client-supplied one: an
        # endpoint that could target any address would be an open mail-relay-testing primitive.
        sender(settings, auth.user.email, subject, body, from_address=from_address)
    except EmailSendError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось отправить письмо, попробуйте ещё раз позже') from error
    auth.user.email_test_sent_at = now
    db.commit()
    if configured:
        return TestSendOut(delivered=True, message=f'Письмо отправлено на {auth.user.email}.')
    return TestSendOut(delivered=False, message='Почтовый провайдер не настроен: письмо записано только в журнал сервера, реальная отправка недоступна.')
