"""Superadmin-only account overview and Keycloak pending-registration approval
(Настройки → Пользователи и роли; Настройки → Аккаунт).

"Pending registration" means: a Keycloak account exists (the person can sign in) but has none of
the CRM roles yet, so the CRM never created a local `users` row for them and they have no access
to anything past the login screen. Approving one just grants the baseline `crm-user` role —
matching this project's deliberately simple RBAC model (one superadmin, everyone else is a plain
crm-user unless promoted later by hand, see docs/decisions.md). There is no separate "reject"
action: leaving an account unapproved already has the same effect (no CRM access), and Keycloak
itself is the place to disable an account outright if that's ever needed.

Every method here needs `request.app.state.keycloak_admin.is_configured()` — when the Keycloak
Admin API credentials aren't set (the default in local dev unless deploy/local/api.env has them),
pending-registration data is reported as unavailable rather than silently empty, so the UI can
tell the two states apart (see docs/api/admin.md).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .keycloak_admin import KeycloakAdminError
from .models import User
from .oidc import CRM_ROLES

router = APIRouter(prefix='/api/v1/admin', tags=['Администрирование'])
superadmin_only = require_roles(ROLE_SUPERADMIN)


class AdminUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    roles: list[str]
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminUsersOut(BaseModel):
    total: int
    users: list[AdminUserOut]


def _admin_user_out(row):
    return AdminUserOut(
        id=row.id, email=row.email, full_name=row.full_name, roles=sorted(row.roles),
        is_active=row.is_active, created_at=row.created_at, last_login_at=row.last_login_at,
    )


@router.get(
    '/users', response_model=AdminUsersOut, summary='Все пользователи CRM',
    dependencies=[Depends(superadmin_only)],
)
def list_all_users(db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.full_name)).all()
    return AdminUsersOut(total=len(rows), users=[_admin_user_out(r) for r in rows])


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
