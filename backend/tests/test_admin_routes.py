import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import login, make_settings

USERS_PATH = '/api/v1/admin/users'
PENDING_PATH = '/api/v1/admin/pending-registrations'


@pytest.fixture
def configured_app(database_url, keycloak):
    # Overrides conftest's `app` fixture: this one has Keycloak Admin API credentials set, so
    # is_configured() is True and pending-registration tests can exercise the real code path.
    return create_app(
        make_settings(
            database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
            keycloak_admin_client_secret=ADMIN_CLIENT_SECRET, keycloak_admin_base_url=ADMIN_BASE_URL,
        ),
        http_client=keycloak.http_client(),
    )


@pytest.fixture
def configured_client(configured_app):
    with TestClient(configured_app) as test_client:
        yield test_client


def test_only_superadmin_can_list_users(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    assert client.get(USERS_PATH).status_code == 403


def test_only_superadmin_can_list_pending_registrations(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    assert client.get(PENDING_PATH).status_code == 403


def test_only_superadmin_can_approve(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    assert client.post(f'{PENDING_PATH}/some-id/approve').status_code == 403


def test_lists_real_crm_users_with_a_total_count(client, keycloak):
    login(client, keycloak, roles=('crm-user',), subject='kc-user-2', email='member@demo.local', name='Иван Член')
    login(client, keycloak, roles=('crm-superadmin',), subject='kc-user-3')
    response = client.get(USERS_PATH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['total'] >= 2
    emails = {u['email'] for u in body['users']}
    assert {'member@demo.local'} <= emails
    member = next(u for u in body['users'] if u['email'] == 'member@demo.local')
    assert member['roles'] == ['crm-user']
    assert member['is_active'] is True


def test_pending_registrations_unavailable_without_admin_credentials(client, keycloak):
    login(client, keycloak, roles=('crm-superadmin',))
    response = client.get(PENDING_PATH)
    assert response.status_code == 200, response.text
    assert response.json() == {'available': False, 'pending': []}


def test_pending_registrations_lists_keycloak_users_with_no_crm_role(configured_client, keycloak):
    keycloak.add_admin_user(id='kc-pending-1', email='pending@demo.local', username='pending', roles=[])
    keycloak.add_admin_user(id='kc-active-1', email='active@demo.local', username='active', roles=['crm-user'])
    keycloak.add_admin_user(id='kc-service-1', email='', username='service-account-edu-crm-admin', roles=[])
    login(configured_client, keycloak, roles=('crm-superadmin',))
    response = configured_client.get(PENDING_PATH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['available'] is True
    assert [p['keycloak_id'] for p in body['pending']] == ['kc-pending-1']
    assert body['pending'][0]['email'] == 'pending@demo.local'


def test_approving_grants_the_crm_user_role(configured_client, keycloak):
    keycloak.add_admin_user(id='kc-pending-2', email='newbie@demo.local', username='newbie', roles=[])
    login(configured_client, keycloak, roles=('crm-superadmin',))
    response = configured_client.post(f'{PENDING_PATH}/kc-pending-2/approve')
    assert response.status_code == 204, response.text
    assert keycloak.admin_users['kc-pending-2']['roles'] == ['crm-user']


def test_approving_without_admin_credentials_configured_is_a_service_error(client, keycloak):
    login(client, keycloak, roles=('crm-superadmin',))
    response = client.post(f'{PENDING_PATH}/whatever/approve')
    assert response.status_code == 503


def test_approving_surfaces_a_keycloak_failure_as_a_service_error(configured_client, keycloak):
    login(configured_client, keycloak, roles=('crm-superadmin',))
    keycloak.unavailable = True
    response = configured_client.post(f'{PENDING_PATH}/does-not-exist/approve')
    assert response.status_code == 503
