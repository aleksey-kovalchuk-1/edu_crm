"""Sharing superadmin rights (owner decision 2026-09-29): a superadmin can make an administrator a superadmin; only
the primary superadmin (Irina, PRIMARY_SUPERADMIN_USERNAME) can take superadmin rights away, and nobody can take
hers."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, login, make_settings

USERS = '/api/v1/admin/users'
SUPER = ('crm-superadmin', 'crm-admin', 'crm-supervisor')


@pytest.fixture
def app(database_url, keycloak):
    keycloak.add_admin_user(id='kc-irina', email='irina@mail.ru', username='irina_super_admin', roles=['crm-superadmin'])
    keycloak.add_admin_user(id='kc-olga', email='olga@mail.ru', username='olga', roles=['crm-admin'])
    keycloak.add_admin_user(id='kc-anna', email='anna@mail.ru', username='anna', roles=['crm-user'])
    return create_app(
        make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                      keycloak_admin_client_secret=ADMIN_CLIENT_SECRET, keycloak_admin_base_url=ADMIN_BASE_URL),
        http_client=keycloak.http_client(),
    )


def _as(app, keycloak, subject):
    client = TestClient(app)
    client.__enter__()
    login(client, keycloak, roles=SUPER, subject=subject)
    return client


def test_a_superadmin_makes_an_administrator_a_superadmin(app, keycloak, database_url):
    irina = _as(app, keycloak, 'kc-irina')
    response = irina.post(f'{USERS}/kc-olga/superadmin')
    assert response.status_code == 200, response.text
    assert keycloak.admin_users['kc-olga']['roles'] == ['crm-superadmin']
    assert 'kc-olga' in keycloak.logged_out_users
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent.action).where(AuditEvent.action == 'admin.superadmin_grant'))
    olga_row = next(u for u in irina.get(USERS).json()['users'] if u['username'] == 'olga')
    assert olga_row['roles'] == ['crm-superadmin']


def test_only_administrators_can_be_made_superadmins(app, keycloak):
    irina = _as(app, keycloak, 'kc-irina')
    assert irina.post(f'{USERS}/kc-anna/superadmin').status_code == 409
    assert keycloak.admin_users['kc-anna']['roles'] == ['crm-user']


def test_a_shared_superadmin_can_share_further_but_cannot_revoke(app, keycloak):
    keycloak.admin_users['kc-olga']['roles'] = ['crm-superadmin']
    keycloak.add_admin_user(id='kc-petr', email='petr@mail.ru', username='petr', roles=['crm-admin'])
    olga = _as(app, keycloak, 'kc-olga')
    assert olga.post(f'{USERS}/kc-petr/superadmin').status_code == 200
    assert olga.delete(f'{USERS}/kc-petr/superadmin').status_code == 403
    assert olga.delete(f'{USERS}/kc-irina/superadmin').status_code == 403
    assert keycloak.admin_users['kc-petr']['roles'] == ['crm-superadmin']
    assert olga.get(USERS).json()['can_revoke_superadmin'] is False


def test_only_irina_revokes_and_the_person_becomes_an_administrator_again(app, keycloak, database_url):
    keycloak.admin_users['kc-olga']['roles'] = ['crm-superadmin']
    irina = _as(app, keycloak, 'kc-irina')
    body = irina.get(USERS).json()
    assert body['can_revoke_superadmin'] is True
    assert {u['username']: u['primary_superadmin'] for u in body['users']}['irina_super_admin'] is True
    assert irina.delete(f'{USERS}/kc-olga/superadmin').status_code == 204
    assert keycloak.admin_users['kc-olga']['roles'] == ['crm-admin']
    assert 'kc-olga' in keycloak.logged_out_users
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent.action).where(AuditEvent.action == 'admin.superadmin_revoke'))


def test_nobody_can_revoke_irinas_superadmin_rights(app, keycloak):
    irina = _as(app, keycloak, 'kc-irina')
    assert irina.delete(f'{USERS}/kc-irina/superadmin').status_code == 409
    assert keycloak.admin_users['kc-irina']['roles'] == ['crm-superadmin']


def test_revoking_from_someone_who_is_not_a_superadmin_is_a_conflict(app, keycloak):
    irina = _as(app, keycloak, 'kc-irina')
    assert irina.delete(f'{USERS}/kc-olga/superadmin').status_code == 409


def test_administrators_cannot_share_superadmin_rights(app, keycloak):
    client = TestClient(app)
    client.__enter__()
    login(client, keycloak, roles=('crm-admin',), subject='kc-olga')
    keycloak.add_admin_user(id='kc-petr', email='petr@mail.ru', username='petr', roles=['crm-admin'])
    assert client.post(f'{USERS}/kc-petr/superadmin').status_code == 403
    assert keycloak.admin_users['kc-petr']['roles'] == ['crm-admin']


def test_a_failed_grant_leaves_the_administrator_role(app, keycloak):
    irina = _as(app, keycloak, 'kc-irina')
    keycloak.fail_role_assignment = True
    assert irina.post(f'{USERS}/kc-olga/superadmin').status_code == 503
    assert keycloak.admin_users['kc-olga']['roles'] == ['crm-admin']
