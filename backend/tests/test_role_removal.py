"""Removing a KAM's or administrator's CRM role (owner request 2026-09-29, «Изменить роль» → «Удалить роль»): the
person loses CRM access at once, their sessions end, and they reappear in «Заявки на доступ». Supervisors and the
superadmin stay protected."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent, User
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, login, make_settings

USERS = '/api/v1/admin/users'
PENDING = '/api/v1/admin/pending-registrations'


@pytest.fixture
def app(database_url, keycloak):
    return create_app(
        make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                      keycloak_admin_client_secret=ADMIN_CLIENT_SECRET, keycloak_admin_base_url=ADMIN_BASE_URL),
        http_client=keycloak.http_client(),
    )


@pytest.fixture
def client(app, keycloak):
    with TestClient(app) as test_client:
        login(test_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')
        yield test_client


@pytest.mark.parametrize('role', ['crm-user', 'crm-supervisor', 'crm-admin'])
def test_removing_the_role_takes_access_away_and_returns_them_to_the_queue(app, client, keycloak, database_url, role):
    keycloak.add_admin_user(id='kc-anna', email='anna@mail.ru', username='anna', roles=[role])
    with TestClient(app) as anna:
        login(anna, keycloak, roles=(role,), subject='kc-anna', email='anna@mail.ru')
        assert anna.get('/api/v1/auth/me').status_code == 200

        response = client.delete(f'{USERS}/kc-anna/role')
        assert response.status_code == 204, response.text

        assert keycloak.admin_users['kc-anna']['roles'] == []
        assert 'kc-anna' in keycloak.logged_out_users
        assert anna.get('/api/v1/auth/me').status_code == 401
    assert [p['keycloak_id'] for p in client.get(PENDING).json()['pending']] == ['kc-anna']
    assert 'anna' not in [u['username'] for u in client.get(USERS).json()['users']]
    with database(database_url) as db:
        assert db.scalar(select(User.roles).where(User.keycloak_sub == 'kc-anna')) == []
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'admin.user_role_remove'))
        assert event.payload == {'keycloak_id': 'kc-anna', 'old_roles': [role]}


@pytest.mark.parametrize('roles', [['crm-superadmin'], ['crm-superadmin', 'crm-admin']])
def test_protected_roles_cannot_be_removed(client, keycloak, roles):
    keycloak.add_admin_user(id='kc-head', email='head@mail.ru', username='head', roles=roles)
    assert client.delete(f'{USERS}/kc-head/role').status_code == 409
    assert keycloak.admin_users['kc-head']['roles'] == roles


def test_removing_from_someone_without_a_role_is_a_conflict(client, keycloak):
    keycloak.add_admin_user(id='kc-new', email='new@mail.ru', username='new', roles=[])
    assert client.delete(f'{USERS}/kc-new/role').status_code == 409


def test_a_failed_removal_restores_the_role(client, keycloak):
    keycloak.add_admin_user(id='kc-anna', email='anna@mail.ru', username='anna', roles=['crm-user'])
    keycloak.fail_role_removal = True
    assert client.delete(f'{USERS}/kc-anna/role').status_code == 503
    assert keycloak.admin_users['kc-anna']['roles'] == ['crm-user']


def test_only_the_superadmin_can_remove_a_role(app, keycloak):
    keycloak.add_admin_user(id='kc-anna', email='anna@mail.ru', username='anna', roles=['crm-user'])
    with TestClient(app) as other:
        login(other, keycloak, roles=('crm-admin',), subject='kc-admin')
        assert other.delete(f'{USERS}/kc-anna/role').status_code == 403
    assert keycloak.admin_users['kc-anna']['roles'] == ['crm-user']
