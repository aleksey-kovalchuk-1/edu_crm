"""One-time, repeatable reconciliation of the existing demonstration identities.

Use preview before --apply. Existing Keycloak subject IDs and CRM foreign keys are retained.
Temporary passwords are written only to a caller-specified private file, never to stdout.
"""
import argparse
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from .audit import record_event
from .keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from .models import User, UserSession, utcnow
from .settings import database_url_from_environment, load_settings


@dataclass(frozen=True)
class ExistingAccount:
    old_username: str
    username: str
    first_name: str
    last_name: str
    roles: frozenset[str]

    @property
    def email(self):
        return f'{self.username}@educrm-demo.ru'


# Demote the former second head before granting Irina the sole supervisor role.
EXISTING = (
    ExistingAccount('pavel.demo@educrm-demo.ru', 'manager_2', 'Менеджер', '2', frozenset({'crm-user'})),
    ExistingAccount('irina.demo@educrm-demo.ru', 'irina_super_admin', 'Ирина', 'Руководитель',
                    frozenset({'crm-superadmin', 'crm-supervisor', 'crm-admin'})),
    ExistingAccount('anna.demo@educrm-demo.ru', 'manager_1', 'Менеджер', '1', frozenset({'crm-user'})),
)
NEW_ADMINS = ('admin_1', 'admin_2')
CRM_ROLES = frozenset({'crm-user', 'crm-supervisor', 'crm-admin', 'crm-superadmin'})


def _accounts(client):
    accounts = []
    while True:
        page = client.list_users(first=len(accounts), max_results=200)
        accounts.extend(page)
        if len(page) < 200:
            return accounts


def _write_credentials(file, values):
    file.seek(0)
    json.dump(values, file, ensure_ascii=False, indent=2)
    file.truncate()
    file.flush()
    os.fsync(file.fileno())


def reconcile_demo_accounts(db, client, *, apply=False, credentials_out=None,
                            password_factory=lambda: secrets.token_urlsafe(24)):
    accounts = _accounts(client)
    existing = {}
    for spec in EXISTING:
        matches = [a for a in accounts if a.username in {spec.old_username, spec.username}
                   or (a.username == spec.email and a.email == spec.email)]
        if len(matches) != 1:
            raise ValueError(f'expected one account for {spec.username}, found {len(matches)}')
        existing[spec.username] = matches[0]
        if any(a.id != matches[0].id and (a.username == spec.username or a.email == spec.email) for a in accounts):
            raise ValueError(f'target login or email already belongs to another account: {spec.username}')
    irina_id = existing['irina_super_admin'].id
    pavel_id = existing['manager_2'].id
    if {a.id for a in accounts if 'crm-superadmin' in a.roles} != {irina_id}:
        raise ValueError('Irina must be the one existing superadmin')
    supervisors = {a.id for a in accounts if 'crm-supervisor' in a.roles}
    if not supervisors <= {irina_id, pavel_id}:
        raise ValueError('an unrelated account has the supervisor role')

    new_admins = {}
    for username in NEW_ADMINS:
        email = f'{username}@educrm-demo.ru'
        matches = [a for a in accounts if a.username == username or a.email == email]
        if len(matches) > 1 or (matches and (matches[0].username not in {username, email} or
                                    matches[0].email != email or set(matches[0].roles) & CRM_ROLES != {'crm-admin'})):
            raise ValueError(f'conflicting existing administrator account: {username}')
        new_admins[username] = matches[0] if matches else None

    renamed = 0
    role_changes = 0
    for spec in EXISTING:
        account = existing[spec.username]
        if (account.username, account.email, account.first_name, account.last_name) != (
            spec.username, spec.email, spec.first_name, spec.last_name,
        ):
            renamed += 1
        role_changes += len(spec.roles - set(account.roles)) + len((set(account.roles) & CRM_ROLES) - spec.roles)
    renamed += sum(account is not None and account.username != username
                   for username, account in new_admins.items())
    result = {'renamed': renamed, 'created': sum(a is None for a in new_admins.values()),
              'role_changes': role_changes}
    if not apply:
        return result

    changing = any(result.values())
    if changing and credentials_out is None:
        raise ValueError('credentials_out is required when applying account changes')
    if changing:
        realm = client.get_realm_login_settings()
        if realm['registrationEmailAsUsername']:
            raise ValueError('disable Keycloak email-as-username before changing demonstration accounts')
        if renamed and not realm['editUsernameAllowed']:
            raise ValueError('temporarily enable Keycloak editUsernameAllowed for existing login renames')
    credential_file = None
    credentials = {}
    try:
        if changing:
            path = Path(credentials_out)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            credential_file = os.fdopen(descriptor, 'w', encoding='utf-8')
        for spec in EXISTING:
            account = existing[spec.username]
            current_roles = set(account.roles) & CRM_ROLES
            identity_changed = (account.username, account.email, account.first_name, account.last_name) != (
                spec.username, spec.email, spec.first_name, spec.last_name,
            )
            # Role changes must also invalidate the old session; username-only changes do too.
            changed = identity_changed or current_roles != spec.roles
            if identity_changed:
                client.update_user(account.id, username=spec.username, email=spec.email,
                                   first_name=spec.first_name, last_name=spec.last_name)
            for role in sorted(spec.roles - current_roles):
                client.assign_realm_role(account.id, role)
            for role in sorted(current_roles - spec.roles):
                client.remove_realm_role(account.id, role)
            actual = client.get_user(account.id)
            if (actual.username != spec.username or actual.email != spec.email
                    or set(actual.roles) & CRM_ROLES != spec.roles):
                raise ValueError(f'Keycloak did not save the expected login and roles for {spec.username}')
            if changed:
                password = password_factory()
                credentials[spec.username] = password
                _write_credentials(credential_file, credentials)
                client.set_temporary_password(account.id, password)
                client.logout_user(account.id)
            local = db.scalar(select(User).where(User.keycloak_sub == account.id))
            if local is not None:
                local.email = spec.email
                local.full_name = f'{spec.first_name} {spec.last_name}'
                local.roles = sorted(spec.roles)
                if changed:
                    db.execute(update(UserSession).where(
                        UserSession.user_id == local.id, UserSession.revoked_at.is_(None),
                    ).values(revoked_at=utcnow()))

        for username in NEW_ADMINS:
            account = new_admins[username]
            if account is None:
                password = password_factory()
                credentials[username] = password
                _write_credentials(credential_file, credentials)
                user_id = client.create_user(
                    username=username, email=f'{username}@educrm-demo.ru',
                    first_name='Администратор', last_name=username[-1], temporary_password=password,
                )
                try:
                    client.assign_realm_role(user_id, 'crm-admin')
                    client.set_user_enabled(user_id, True)
                    actual = client.get_user(user_id)
                    if (actual.username != username or actual.email != f'{username}@educrm-demo.ru'
                            or set(actual.roles) & CRM_ROLES != {'crm-admin'} or not actual.enabled):
                        raise KeycloakAdminError('Keycloak did not save the new administrator account')
                except KeycloakAdminError:
                    try:
                        client.delete_user(user_id)
                    except KeycloakAdminError:
                        pass  # The partial account was created disabled; operator can retry after inspection.
                    raise
                db.add(User(
                    keycloak_sub=user_id, email=f'{username}@educrm-demo.ru',
                    full_name=f'Администратор {username[-1]}', roles=['crm-admin'], is_active=True,
                ))
            else:
                if account.username != username:
                    password = password_factory()
                    credentials[username] = password
                    _write_credentials(credential_file, credentials)
                    client.update_user(account.id, username=username, email=account.email,
                                       first_name='Администратор', last_name=username[-1])
                    client.set_temporary_password(account.id, password)
                    client.logout_user(account.id)
                actual = client.get_user(account.id)
                if (actual.username != username or actual.email != f'{username}@educrm-demo.ru'
                        or set(actual.roles) & CRM_ROLES != {'crm-admin'} or not actual.enabled):
                    raise ValueError(f'Keycloak did not save the expected administrator {username}')
                local = db.scalar(select(User).where(User.keycloak_sub == account.id))
                if local is None:
                    db.add(User(keycloak_sub=account.id, email=account.email,
                                full_name=f'Администратор {username[-1]}', roles=['crm-admin'], is_active=True))

        if client.count_users_with_role('crm-superadmin') != 1 or client.count_users_with_role('crm-supervisor') != 1:
            raise ValueError('privileged role count changed unexpectedly; stop before committing')
        if changing:
            record_event(db, None, None, 'admin.demo_account_reconcile', entity_type='keycloak_user',
                         summary='Обновлены демонстрационные роли и логины по запросу владельца', payload=result)
        db.flush()
        return result
    finally:
        if credential_file is not None:
            credential_file.close()


def main():
    parser = argparse.ArgumentParser(description='Preview or reconcile the demo account roster')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--credentials-out', type=Path, help='new mode-0600 file for one-time passwords')
    args = parser.parse_args()
    settings = load_settings()
    engine = create_engine(database_url_from_environment())
    try:
        with httpx.Client(timeout=10) as http, Session(engine) as db:
            client = KeycloakAdminClient(
                base_url=settings.keycloak_admin_base_url,
                client_id=settings.keycloak_admin_client_id,
                client_secret=settings.keycloak_admin_client_secret, http_client=http,
            )
            result = reconcile_demo_accounts(db, client, apply=args.apply, credentials_out=args.credentials_out)
            if args.apply:
                db.commit()
            print(json.dumps({'mode': 'applied' if args.apply else 'preview', **result}))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
