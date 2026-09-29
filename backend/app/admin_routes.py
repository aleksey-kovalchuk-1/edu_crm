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

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .keycloak_admin import KeycloakAdminConflict, KeycloakAdminError, KeycloakAdminNotFound
from .models import User, UserSession, utcnow
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


UserId = Annotated[str, Path(pattern=r'^[A-Za-z0-9_-]{1,80}$')]


def _account_for_admin_action(keycloak_admin, keycloak_id):
    if not keycloak_admin.is_configured():
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Управление пользователями не подключено')
    try:
        account = keycloak_admin.get_user(keycloak_id)
    except KeycloakAdminNotFound as error:
        raise AppError(ErrorCode.NOT_FOUND, 'Учётная запись не найдена') from error
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Сервис входа временно недоступен') from error
    if not account.email:
        raise AppError(ErrorCode.NOT_FOUND, 'Учётная запись не найдена')
    return account


def _revoke_crm_sessions(db, keycloak_id):
    local = db.scalar(select(User).where(User.keycloak_sub == keycloak_id))
    if local is not None:
        db.execute(update(UserSession).where(
            UserSession.user_id == local.id, UserSession.revoked_at.is_(None),
        ).values(revoked_at=utcnow()))
    return local


# Steps a self-registered person may still owe Keycloak; granting access e-mails them a link for these (D-241).
SETUP_ACTIONS = ('VERIFY_EMAIL', 'UPDATE_PASSWORD')
SETUP_LINK_SECONDS = 12 * 60 * 60


def _setup_actions(account):
    return [action for action in SETUP_ACTIONS if action in account.required_actions]


def _send_password_setup(db, request, auth, keycloak_admin, account):
    """E-mails Keycloak's «confirm the address and set a password» link; 'sent', 'not_needed' or 'failed'."""
    actions = _setup_actions(account)
    if not actions:
        return 'not_needed'
    try:
        keycloak_admin.send_actions_email(account.id, actions, lifespan_seconds=SETUP_LINK_SECONDS)
    except KeycloakAdminError:
        logger.exception('Could not send the password setup e-mail to %s', account.id)
        return 'failed'
    record_event(
        db, request, auth.user, 'admin.password_setup_email', entity_type='keycloak_user', entity_id=account.id,
        summary=f'Отправлено письмо для установки пароля пользователю {account.username}',
        payload={'keycloak_id': account.id, 'actions': actions},
    )
    return 'sent'


def _all_keycloak_accounts(client):
    accounts = []
    while True:
        page = client.list_users(first=len(accounts), max_results=200)
        accounts.extend(page)
        if len(page) < 200:
            return accounts


@router.post('/users', response_model=CreatedAdminUser, status_code=201,
             summary='Создать учётную запись менеджера или администратора')
def create_admin_user(
    data: NewAdminUser, request: Request, response: Response,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    if not keycloak_admin.is_configured():
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Управление пользователями не подключено')
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


class RoleChangeIn(BaseModel):
    role: Literal['crm-user', 'crm-admin']


class ChangedRole(BaseModel):
    keycloak_id: str
    username: str
    role: str
    # Granting a first CRM role to someone who hasn't confirmed their address or set a password e-mails them a link.
    password_setup: Literal['sent', 'not_needed', 'failed'] = 'not_needed'


@router.patch('/users/{keycloak_id}/role', response_model=ChangedRole,
              summary='Изменить роль зарегистрированного пользователя')
def change_user_role(
    keycloak_id: UserId, data: RoleChangeIn, request: Request,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    account = _account_for_admin_action(keycloak_admin, keycloak_id)
    previous = set(account.roles) & CRM_ROLES
    if previous & {'crm-supervisor', 'crm-superadmin'}:
        raise AppError(ErrorCode.CONFLICT, 'Роль руководителя и главного администратора защищена')
    if previous == {data.role}:
        return ChangedRole(keycloak_id=keycloak_id, username=account.username, role=data.role)

    removed = []
    added = False
    try:
        # Remove an old administrator role first so a failed demotion never leaves it elevated.
        for old_role in sorted(previous - {data.role}):
            keycloak_admin.remove_realm_role(keycloak_id, old_role)
            removed.append(old_role)
        if data.role not in previous:
            keycloak_admin.assign_realm_role(keycloak_id, data.role)
            added = True
        actual = keycloak_admin.get_user(keycloak_id)
        if set(actual.roles) & CRM_ROLES != {data.role}:
            raise KeycloakAdminError('Keycloak did not save the requested CRM role')
        keycloak_admin.logout_user(keycloak_id)
    except KeycloakAdminError as error:
        # Best effort compensation if Keycloak rejected a later step. A failed demotion
        # must be visible as an error, never reported as a successful role update.
        if added:
            try:
                keycloak_admin.remove_realm_role(keycloak_id, data.role)
            except KeycloakAdminError:
                logger.exception('Could not undo the new role on %s', keycloak_id)
        for old_role in removed:
            try:
                keycloak_admin.assign_realm_role(keycloak_id, old_role)
            except KeycloakAdminError:
                logger.exception('Could not restore role %s on %s', old_role, keycloak_id)
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось изменить роль; проверьте учётную запись и повторите действие') from error

    local = _revoke_crm_sessions(db, keycloak_id)
    if local is not None:
        local.roles = [data.role]
    record_event(
        db, request, auth.user, 'admin.user_role_change', entity_type='keycloak_user',
        entity_id=keycloak_id, summary=f'Изменена роль пользователя {account.username}',
        payload={'keycloak_id': keycloak_id, 'old_roles': sorted(previous), 'new_role': data.role},
    )
    setup = _send_password_setup(db, request, auth, keycloak_admin, account) if not previous else 'not_needed'
    db.commit()
    return ChangedRole(keycloak_id=keycloak_id, username=account.username, role=data.role, password_setup=setup)


@router.delete('/users/{keycloak_id}/role', status_code=204, summary='Удалить роль CRM (доступ к CRM прекращается)')
def remove_user_role(
    keycloak_id: UserId, request: Request,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    account = _account_for_admin_action(keycloak_admin, keycloak_id)
    previous = set(account.roles) & CRM_ROLES
    if previous & {'crm-supervisor', 'crm-superadmin'}:
        raise AppError(ErrorCode.CONFLICT, 'Роль руководителя и главного администратора защищена')
    if not previous:
        raise AppError(ErrorCode.CONFLICT, 'У пользователя нет роли CRM')

    removed = []
    try:
        for old_role in sorted(previous):
            keycloak_admin.remove_realm_role(keycloak_id, old_role)
            removed.append(old_role)
        if set(keycloak_admin.get_user(keycloak_id).roles) & CRM_ROLES:
            raise KeycloakAdminError('Keycloak still lists a CRM role')
        keycloak_admin.logout_user(keycloak_id)
    except KeycloakAdminError as error:
        for old_role in removed:
            try:
                keycloak_admin.assign_realm_role(keycloak_id, old_role)
            except KeycloakAdminError:
                logger.exception('Could not restore role %s on %s', old_role, keycloak_id)
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось удалить роль; проверьте учётную запись и повторите действие') from error

    local = _revoke_crm_sessions(db, keycloak_id)
    if local is not None:
        local.roles = []
    record_event(
        db, request, auth.user, 'admin.user_role_remove', entity_type='keycloak_user',
        entity_id=keycloak_id, summary=f'Удалена роль CRM у пользователя {account.username}',
        payload={'keycloak_id': keycloak_id, 'old_roles': sorted(previous)},
    )
    db.commit()
    return Response(status_code=204)


class SetupEmailOut(BaseModel):
    sent: bool
    message: str


@router.post('/users/{keycloak_id}/password-setup-email', response_model=SetupEmailOut,
             summary='Отправить письмо для подтверждения адреса и установки пароля')
def send_password_setup_email(
    keycloak_id: UserId, request: Request,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    account = _account_for_admin_action(keycloak_admin, keycloak_id)
    if not _setup_actions(account):
        raise AppError(ErrorCode.CONFLICT, 'Пользователь уже подтвердил адрес и задал пароль')
    if _send_password_setup(db, request, auth, keycloak_admin, account) != 'sent':
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось отправить письмо; попробуйте ещё раз позже')
    db.commit()
    return SetupEmailOut(sent=True, message=f'Письмо для установки пароля отправлено на {account.email}.')


class ResetPasswordOut(BaseModel):
    keycloak_id: str
    username: str
    temporary_password: str


@router.post('/users/{keycloak_id}/reset-password', response_model=ResetPasswordOut,
             summary='Выдать пользователю новый временный пароль')
def reset_user_password(
    keycloak_id: UserId, request: Request, response: Response,
    auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db),
):
    keycloak_admin = request.app.state.keycloak_admin
    account = _account_for_admin_action(keycloak_admin, keycloak_id)
    password = secrets.token_urlsafe(24)
    try:
        keycloak_admin.logout_user(keycloak_id)
        keycloak_admin.set_temporary_password(keycloak_id, password)
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось сбросить пароль; попробуйте ещё раз') from error
    _revoke_crm_sessions(db, keycloak_id)
    record_event(
        db, request, auth.user, 'admin.user_password_reset', entity_type='keycloak_user',
        entity_id=keycloak_id, summary=f'Сброшен пароль пользователя {account.username}',
        payload={'keycloak_id': keycloak_id, 'username': account.username},
    )
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return ResetPasswordOut(keycloak_id=keycloak_id, username=account.username, temporary_password=password)


class AdminUserOut(BaseModel):
    keycloak_id: str
    username: str
    email: str
    full_name: str
    roles: list[str]
    is_active: bool
    last_login_at: datetime | None
    # Hasn't confirmed the address or set a password yet (Keycloak still asks for it).
    setup_pending: bool = False


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
        accounts = _all_keycloak_accounts(keycloak_admin)
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Сервис входа временно недоступен, попробуйте ещё раз позже') from error
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
            setup_pending=bool(_setup_actions(account)),
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
        users = _all_keycloak_accounts(keycloak_admin)
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Сервис входа временно недоступен, попробуйте ещё раз позже') from error
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
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Управление пользователями не подключено')
    try:
        keycloak_admin.assign_realm_role(keycloak_id, 'crm-user')
    except KeycloakAdminError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось одобрить регистрацию, попробуйте ещё раз позже') from error
    record_event(
        db, request, auth.user, 'admin.pending_registration_approve',
        entity_type='keycloak_user', entity_id=keycloak_id,
        summary=f'Одобрена регистрация пользователя {keycloak_id}',
        payload={'keycloak_id': keycloak_id, 'granted_role': 'crm-user'},
    )
    db.commit()
