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
from .errors import AppError, ErrorCode
from .models import EmailSenderIdentity

router = APIRouter(prefix='/api/v1/email-senders', tags=['Отправители писем'])
any_role = require_roles(*ALL_ROLES)
sender_manager = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


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
    if existing is not None:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'email_address', 'message': 'Такой адрес уже добавлен', 'type': 'value_error'}])
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
