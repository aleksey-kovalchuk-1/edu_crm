"""Sender addresses for outgoing university correspondence (spec 2026-09-27, section 2).

Personal addresses: the owner requests one, a crm-supervisor/crm-admin (never the requester) approves it,
and a single-use link mailed to the address confirms the mailbox. Shared addresses: a supervisor/admin
adds one and it is confirmed the same way. Only confirmed ('active'), active, owned-or-shared rows are
usable — see app/sender_addresses.py, which every send and every selection goes through.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .db import get_db
from .email import EmailSendError, send_email
from .errors import AppError, ErrorCode
from .models import EmailSenderIdentity, User, utcnow
from .security import token_hash
from .sender_addresses import INVALID_LINK, RESEND_COOLDOWN_SECONDS, is_usable, issue_confirmation, usable_sender

router = APIRouter(prefix='/api/v1/email-senders', tags=['Отправители писем'])
any_role = require_roles(*ALL_ROLES)
sender_manager = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
TEST_SEND_COOLDOWN_SECONDS = 60
TEST_SEND_COOLDOWN_MESSAGE = 'Тестовое письмо уже отправлено, следующее можно запросить не раньше чем через минуту'
OPEN_STATUSES = ('pending_approval', 'awaiting_confirmation')
ADDRESS_TAKEN = [{'field': 'email_address', 'message': 'Этот адрес уже используется', 'type': 'value_error'}]


class SenderIn(BaseModel):
    email_address: EmailStr
    display_name: DisplayName


class SenderOut(BaseModel):
    id: int
    email_address: str
    display_name: str
    is_active: bool
    status: str
    is_shared: bool
    rejection_reason: str
    usable: bool


class QueueItemOut(SenderOut):
    requested_by: str
    requested_at: datetime | None


class RejectIn(BaseModel):
    reason: Reason = ''


class ConfirmIn(BaseModel):
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ConfirmOut(BaseModel):
    email_address: str


class DeliveryOut(BaseModel):
    delivered: bool
    message: str


def sender_out(row, user=None):
    usable = is_usable(row, user) if user is not None else (row.is_active and row.status == 'active')
    return SenderOut(
        id=row.id, email_address=row.email_address, display_name=row.display_name, is_active=row.is_active,
        status=row.status, is_shared=row.owner_user_id is None, rejection_reason=row.rejection_reason, usable=usable,
    )


def _event(db, request, actor, action, row, summary):
    record_event(db, request, actor, action, entity_type='email_sender_identity', entity_id=row.id,
                 summary=summary, payload={'email_address': row.email_address})


def _reusable(row):
    """An existing row with this address may be taken over only if nobody holds it any more: rejected or
    withdrawn, or deactivated. A stale selection of a taken-over row fails the owner check on send."""
    return row.status == 'rejected' or not row.is_active


@router.get('', response_model=list[SenderOut], summary='Доступные мне адреса отправителей')
def list_senders(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailSenderIdentity).where(or_(
        EmailSenderIdentity.owner_user_id == auth.user.id,
        and_(EmailSenderIdentity.owner_user_id.is_(None), EmailSenderIdentity.is_active.is_(True),
             EmailSenderIdentity.status == 'active'),
    )).order_by(EmailSenderIdentity.display_name)).all()
    return [sender_out(r, auth.user) for r in rows]


@router.post('/requests', response_model=SenderOut, status_code=201, summary='Заявка на личный адрес отправителя')
def request_sender(data: SenderIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    open_request = db.scalar(select(EmailSenderIdentity.id).where(
        EmailSenderIdentity.owner_user_id == auth.user.id, EmailSenderIdentity.status.in_(OPEN_STATUSES),
        EmailSenderIdentity.is_active.is_(True)))
    if open_request is not None:
        raise AppError(ErrorCode.CONFLICT, 'У вас уже есть открытая заявка — дождитесь решения или отзовите её')
    existing = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.email_address == data.email_address))
    if existing is not None and not _reusable(existing):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=ADDRESS_TAKEN)
    row = existing or EmailSenderIdentity(email_address=data.email_address, created_by_user_id=auth.user.id)
    row.display_name = data.display_name
    row.owner_user_id = auth.user.id
    row.status = 'pending_approval'
    row.is_active = True
    row.rejection_reason = ''
    row.requested_by_user_id = auth.user.id
    row.requested_at = utcnow()
    row.approved_by_user_id = None
    row.approved_at = None
    row.confirmation_token_hash = None
    row.confirmation_expires_at = None
    if existing is None:
        db.add(row)
    db.flush()
    _event(db, request, auth.user, 'email_sender.request', row, f'Заявка на адрес отправителя {row.email_address}')
    db.commit()
    return sender_out(row, auth.user)


@router.delete('/requests/{sender_id}', status_code=204, summary='Отозвать свою заявку')
def withdraw_request(sender_id: int, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.id == sender_id).with_for_update())
    if row is None or row.owner_user_id != auth.user.id or row.status not in OPEN_STATUSES:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    row.status = 'rejected'
    row.rejection_reason = 'Заявка отозвана'
    row.confirmation_token_hash = None
    row.confirmation_expires_at = None
    _event(db, request, auth.user, 'email_sender.withdraw', row, f'Заявка на адрес {row.email_address} отозвана')
    db.commit()


@router.get('/queue', response_model=list[QueueItemOut], summary='Заявки на адреса отправителей',
            dependencies=[Depends(sender_manager)])
def queue(db: Session = Depends(get_db)):
    rows = db.execute(
        select(EmailSenderIdentity, User.full_name)
        .outerjoin(User, User.id == EmailSenderIdentity.requested_by_user_id)
        .where(EmailSenderIdentity.status.in_(OPEN_STATUSES), EmailSenderIdentity.is_active.is_(True))
        .order_by(EmailSenderIdentity.requested_at.nulls_last(), EmailSenderIdentity.id)
    ).all()
    return [QueueItemOut(**sender_out(r).model_dump(), requested_by=name or '', requested_at=r.requested_at)
            for r, name in rows]


@router.post('/confirm', response_model=ConfirmOut, summary='Подтвердить адрес по ссылке из письма')
def confirm(data: ConfirmIn, request: Request, db: Session = Depends(get_db)):
    # No session: the token proves control of the mailbox. POST only, so link-prefetching mail scanners
    # never confirm an address just by opening the link.
    row = db.scalar(select(EmailSenderIdentity).where(
        EmailSenderIdentity.confirmation_token_hash == token_hash(data.token)).with_for_update())
    if (row is None or row.status != 'awaiting_confirmation' or not row.is_active
            or row.confirmation_expires_at is None or row.confirmation_expires_at <= utcnow()):
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, INVALID_LINK)
    row.status = 'active'
    row.confirmed_at = utcnow()
    row.confirmation_token_hash = None
    row.confirmation_expires_at = None
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    if owner is not None:
        owner.email_sender_identity_id = row.id
    _event(db, request, owner, 'email_sender.confirm', row, f'Подтверждён адрес отправителя {row.email_address}')
    db.commit()
    return ConfirmOut(email_address=row.email_address)


@router.post('', response_model=SenderOut, status_code=201, summary='Добавить общий адрес отправителя')
def create_sender(data: SenderIn, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    existing = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.email_address == data.email_address))
    if (existing is not None and existing.owner_user_id is None and not existing.is_active
            and existing.status == 'active'):
        # A previously confirmed shared address: reactivation keeps its confirmation (unchanged behavior).
        existing.is_active = True
        existing.display_name = data.display_name
        _event(db, request, auth.user, 'email_sender.reactivate', existing,
               f'Восстановлен отправитель писем «{existing.display_name}» ({existing.email_address})')
        db.commit()
        return sender_out(existing)
    if existing is not None and not _reusable(existing):
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'email_address', 'message': 'Такой адрес уже добавлен', 'type': 'value_error'}])
    row = existing or EmailSenderIdentity(email_address=data.email_address)
    row.display_name = data.display_name
    row.owner_user_id = None
    row.is_active = True
    row.status = 'awaiting_confirmation'
    row.rejection_reason = ''
    row.created_by_user_id = auth.user.id
    row.requested_by_user_id = auth.user.id
    row.requested_at = utcnow()
    row.approved_by_user_id = auth.user.id
    row.approved_at = utcnow()
    if existing is None:
        db.add(row)
    db.flush()
    issue_confirmation(request, row)
    _event(db, request, auth.user, 'email_sender.create', row,
           f'Добавлен отправитель писем «{row.display_name}» ({row.email_address})')
    db.commit()
    return sender_out(row)


def _open_row(db, sender_id, status):
    row = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.id == sender_id).with_for_update())
    if row is None or row.status != status or not row.is_active:
        raise AppError(ErrorCode.CONFLICT, 'Заявка уже обработана или недоступна')
    return row


@router.post('/{sender_id}/approve', response_model=DeliveryOut, summary='Одобрить заявку и отправить письмо подтверждения')
def approve(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = _open_row(db, sender_id, 'pending_approval')
    if row.requested_by_user_id == auth.user.id:
        raise AppError(ErrorCode.FORBIDDEN, 'Нельзя одобрить собственную заявку')
    row.status = 'awaiting_confirmation'
    row.approved_by_user_id = auth.user.id
    row.approved_at = utcnow()
    delivered, message = issue_confirmation(request, row)
    _event(db, request, auth.user, 'email_sender.approve', row, f'Одобрен адрес отправителя {row.email_address}')
    db.commit()
    return DeliveryOut(delivered=delivered, message=message)


@router.post('/{sender_id}/reject', status_code=204, summary='Отклонить заявку')
def reject(sender_id: int, data: RejectIn, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = _open_row(db, sender_id, 'pending_approval')
    row.status = 'rejected'
    row.rejection_reason = data.reason
    _event(db, request, auth.user, 'email_sender.reject', row, f'Отклонён адрес отправителя {row.email_address}')
    db.commit()


@router.post('/{sender_id}/resend', response_model=DeliveryOut, summary='Повторить письмо подтверждения')
def resend(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = _open_row(db, sender_id, 'awaiting_confirmation')
    if row.confirmation_sent_at and (utcnow() - row.confirmation_sent_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        raise AppError(ErrorCode.RATE_LIMITED, 'Письмо уже отправлено, повторить можно не раньше чем через минуту')
    delivered, message = issue_confirmation(request, row)
    _event(db, request, auth.user, 'email_sender.confirmation_resent', row,
           f'Повторно отправлено подтверждение на {row.email_address}')
    db.commit()
    return DeliveryOut(delivered=delivered, message=message)


@router.delete('/{sender_id}', status_code=204, summary='Деактивировать адрес отправителя')
def deactivate_sender(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = db.get(EmailSenderIdentity, sender_id)
    if row is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    row.is_active = False
    row.confirmation_token_hash = None
    row.confirmation_expires_at = None
    _event(db, request, auth.user, 'email_sender.deactivate', row,
           f'Деактивирован отправитель писем «{row.display_name}» ({row.email_address})')
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
    now = utcnow()
    if auth.user.email_test_sent_at is not None and (now - auth.user.email_test_sent_at).total_seconds() < TEST_SEND_COOLDOWN_SECONDS:
        raise AppError(ErrorCode.RATE_LIMITED, TEST_SEND_COOLDOWN_MESSAGE)
    # Checked immediately before sending: a selection that became unusable is refused, never replaced.
    from_identity = usable_sender(db, auth.user, auth.user.email_sender_identity_id) if auth.user.email_sender_identity_id else None
    from_label = from_identity.email_address if from_identity else (settings.email_sender_address or settings.email_sender_name)
    from_address = from_identity.email_address if from_identity else (settings.email_sender_address or None)
    subject = 'Тестовое письмо UniCRM'
    body = f'Это тестовое письмо, отправленное от имени «{from_label}». Если вы получили его, отправка почты настроена верно.'
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
