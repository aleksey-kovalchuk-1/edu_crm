"""Superadmin-only account overview, creation and Keycloak pending-registration approval
(Настройки → Пользователи и роли; Настройки → Аккаунт).

"Pending registration" means: a Keycloak account exists (the person can sign in) but has none of
the CRM roles yet, so the CRM never created a local `users` row for them and they have no access
to anything past the login screen. Approving one grants the baseline `crm-user` role. Only the
superadmin can create a new manager or administrator through this API. There is no separate "reject"
action: leaving an account unapproved already has the same effect (no CRM access), and Keycloak
itself is the place to disable an account outright if that's ever needed.

Every method here needs `request.app.state.keycloak_admin.is_configured()` — when the Keycloak
Admin API credentials aren't set (the default in local dev unless deploy/local/api.env has them),
pending-registration data is reported as unavailable rather than silently empty, so the UI can
tell the two states apart (see docs/api/admin.md).
"""
import logging
import secrets
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .keycloak_admin import KeycloakAdminConflict, KeycloakAdminError
from .models import User
from .oidc import CRM_ROLES

router = APIRouter(prefix='/api/v1/admin', tags=['Администрирование'])
superadmin_only = require_roles(ROLE_SUPERADMIN)
logger = logging.getLogger(__name__)


class NewAdminUser(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=40, pattern=r'^[a-z][a-z0-9._-]+$')]
    email: EmailStr
    first_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    role: Literal['crm-user', 'crm-admin']


class CreatedAdminUser(BaseModel):
    keycloak_id: str
    username: str
    email: str
    role: str
    temporary_password: str


@router.post('/users', response_model=CreatedAdminUser, status_code=201,
             summary='Создать учётную запись менеджера или администратора')
def create_admin_user(
    data: NewAdminUser, request: Request, response: Response,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    if not keycloak_admin.is_configured():
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Управление пользователями Keycloak не настроено')
    password = secrets.token_urlsafe(24)
    user_id = None
    try:
        user_id = keycloak_admin.create_user(
            username=data.username, email=str(data.email), first_name=data.first_name,
            last_name=data.last_name, temporary_password=password,
        )
        keycloak_admin.assign_realm_role(user_id, data.role)
        user = User(
            keycloak_sub=user_id, email=str(data.email),
            full_name=f'{data.first_name} {data.last_name}', roles=[data.role], is_active=True,
        )
        db.add(user)
        db.flush()
        record_event(
            db, request, auth.user, 'admin.user_create', entity_type='keycloak_user', entity_id=user_id,
            summary=f'Создана учётная запись {data.username}',
            payload={'keycloak_id': user_id, 'username': data.username, 'role': data.role},
        )
        keycloak_admin.set_user_enabled(user_id, True)
        db.commit()
    except KeycloakAdminConflict as error:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, 'Логин или почта уже используются') from error
    except (KeycloakAdminError, SQLAlchemyError) as error:
        db.rollback()
        if user_id is not None:
            try:
                keycloak_admin.delete_user(user_id)
            except KeycloakAdminError:
                logger.exception('Could not remove failed Keycloak account %s', user_id)
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось создать учётную запись') from error
    response.headers['Cache-Control'] = 'no-store'
    return CreatedAdminUser(
        keycloak_id=user_id, username=data.username, email=str(data.email),
        role=data.role, temporary_password=password,
    )


class AdminUserOut(BaseModel):
    keycloak_id: str
    username: str
    email: str
    full_name: str
    roles: list[str]
    is_active: bool
    last_login_at: datetime | None


class AdminUsersOut(BaseModel):
    available: bool
    total: int
    users: list[AdminUserOut]


@router.get(
    '/users', response_model=AdminUsersOut, summary='Все пользователи CRM',
    dependencies=[Depends(superadmin_only)],
)
def list_all_users(request: Request, db: Session = Depends(get_db)):
    keycloak_admin = request.app.state.keycloak_admin
    if not keycloak_admin.is_configured():
        return AdminUsersOut(available=False, total=0, users=[])
    try:
        accounts = []
        while True:
            page = keycloak_admin.list_users(first=len(accounts), max_results=200)
            accounts.extend(page)
            if len(page) < 200:
                break
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Keycloak временно недоступен, попробуйте ещё раз позже') from error
    accounts = [account for account in accounts if account.email and not CRM_ROLES.isdisjoint(account.roles)]
    local_rows = db.scalars(select(User).where(User.keycloak_sub.in_([account.id for account in accounts]))).all()
    local_by_sub = {row.keycloak_sub: row for row in local_rows}
    users = []
    for account in accounts:
        local = local_by_sub.get(account.id)
        name = f'{account.first_name} {account.last_name}'.strip() or (local.full_name if local else account.username)
        users.append(AdminUserOut(
            keycloak_id=account.id, username=account.username, email=account.email,
            full_name=name, roles=sorted(CRM_ROLES.intersection(account.roles)),
            is_active=account.enabled, last_login_at=local.last_login_at if local else None,
        ))
    users.sort(key=lambda row: (row.full_name.casefold(), row.username))
    return AdminUsersOut(available=True, total=len(users), users=users)


class PendingRegistrationOut(BaseModel):
    keycloak_id: str
    email: str
    username: str


class PendingRegistrationsOut(BaseModel):
    # False when the Keycloak Admin API isn't configured in this environment — the frontend must
    # show "unavailable", not an empty "no pending registrations" list, per the project's standing
    # rule against fabricating a data source that isn't actually there.
    available: bool
    pending: list[PendingRegistrationOut]


@router.get(
    '/pending-registrations', response_model=PendingRegistrationsOut,
    summary='Учётные записи Keycloak без роли CRM', dependencies=[Depends(superadmin_only)],
)
def list_pending_registrations(request: Request):
    keycloak_admin = request.app.state.keycloak_admin
    if not keycloak_admin.is_configured():
        return PendingRegistrationsOut(available=False, pending=[])
    try:
        users = keycloak_admin.list_users()
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Keycloak временно недоступен, попробуйте ещё раз позже') from error
    # No email (e.g. the edu-crm-admin service account itself) can't be a pending human registration.
    pending = [u for u in users if u.email and CRM_ROLES.isdisjoint(u.roles)]
    return PendingRegistrationsOut(
        available=True,
        pending=[PendingRegistrationOut(keycloak_id=u.id, email=u.email, username=u.username) for u in pending],
    )


@router.post(
    '/pending-registrations/{keycloak_id}/approve', status_code=204,
    summary='Одобрить регистрацию (выдать роль crm-user)',
)
def approve_pending_registration(
    keycloak_id: str, request: Request,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    if not keycloak_admin.is_configured():
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Управление пользователями Keycloak не настроено')
    try:
        keycloak_admin.assign_realm_role(keycloak_id, 'crm-user')
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось одобрить регистрацию, попробуйте ещё раз позже') from error
    record_event(
        db, request, auth.user, 'admin.pending_registration_approve',
        entity_type='keycloak_user', entity_id=keycloak_id,
        summary=f'Одобрена регистрация пользователя Keycloak {keycloak_id}',
        payload={'keycloak_id': keycloak_id, 'granted_role': 'crm-user'},
    )
    db.commit()
