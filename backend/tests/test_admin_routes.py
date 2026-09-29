import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent, User, UserSession
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, login, make_settings

USERS_PATH = '/api/v1/admin/users'
PENDING_PATH = '/api/v1/admin/pending-registrations'
CREATE_PAYLOAD = {
    'username': 'admin_1', 'email': 'admin_1@educrm-demo.ru',
    'first_name': 'Администратор', 'last_name': 'Один', 'role': 'crm-admin',
}


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


def test_lists_real_crm_users_with_a_total_count(configured_client, keycloak):
    keycloak.add_admin_user(id='kc-user-2', email='member@demo.local', username='member', roles=['crm-user'])
    keycloak.add_admin_user(id='kc-user-3', email='head@demo.local', username='head', roles=['crm-superadmin'])
    login(configured_client, keycloak, roles=('crm-user',), subject='kc-user-2', email='member@demo.local', name='Иван Член')
    login(configured_client, keycloak, roles=('crm-superadmin',), subject='kc-user-3')
    response = configured_client.get(USERS_PATH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['total'] >= 2
    emails = {u['email'] for u in body['users']}
    assert {'member@demo.local'} <= emails
    member = next(u for u in body['users'] if u['email'] == 'member@demo.local')
    assert member['roles'] == ['crm-user']
    assert member['is_active'] is True


def test_account_directory_uses_keycloak_and_includes_accounts_before_first_login(configured_client, keycloak):
    keycloak.add_admin_user(
        id='kc-new-admin', email='new.admin@educrm-demo.ru', username='new.admin',
        roles=['crm-admin'], first_name='Новый', last_name='Администратор',
    )
    login(configured_client, keycloak, roles=('crm-superadmin',))
    response = configured_client.get(USERS_PATH)
    assert response.status_code == 200, response.text
    assert response.json()['available'] is True
    assert response.json()['total'] == 1
    account = response.json()['users'][0]
    assert account['keycloak_id'] == 'kc-new-admin'
    assert account['username'] == 'new.admin'
    assert account['full_name'] == 'Новый Администратор'
    assert account['roles'] == ['crm-admin']
    assert account['last_login_at'] is None


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


def test_pending_registration_list_includes_accounts_after_first_keycloak_page(configured_client, keycloak):
    for index in range(200):
        keycloak.add_admin_user(id=f'kc-active-{index}', email=f'active-{index}@demo.local',
                                username=f'active-{index}', roles=['crm-user'])
    keycloak.add_admin_user(id='kc-pending-last', email='last@demo.local', username='last', roles=[])
    login(configured_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')

    response = configured_client.get(PENDING_PATH)

    assert response.status_code == 200, response.text
    assert [row['username'] for row in response.json()['pending']] == ['last']


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


def test_superadmin_creates_administrator_with_one_time_temporary_password(configured_client, keycloak, database_url):
    login(configured_client, keycloak, roles=('crm-admin', 'crm-superadmin'))
    response = configured_client.post(USERS_PATH, json=CREATE_PAYLOAD)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created['username'] == 'admin_1'
    assert created['role'] == 'crm-admin'
    assert len(created['temporary_password']) >= 24
    assert response.headers['cache-control'] == 'no-store'
    assert keycloak.admin_users[created['keycloak_id']]['enabled'] is True
    assert keycloak.admin_users[created['keycloak_id']]['roles'] == ['crm-admin']
    assert keycloak.admin_users[created['keycloak_id']]['temporary_password'] == created['temporary_password']
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == created['keycloak_id']))
        assert user is not None and user.roles == ['crm-admin']
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'admin.user_create'))
        assert audit is not None and created['temporary_password'] not in str(audit.payload)


def test_only_superadmin_can_create_accounts(configured_client, keycloak):
    login(configured_client, keycloak, roles=('crm-admin',))
    assert configured_client.post(USERS_PATH, json=CREATE_PAYLOAD).status_code == 403
    assert not keycloak.admin_users


def test_account_creation_accepts_only_manager_or_administrator(configured_client, keycloak):
    login(configured_client, keycloak, roles=('crm-superadmin',))
    for role in ('crm-supervisor', 'crm-superadmin'):
        response = configured_client.post(USERS_PATH, json={**CREATE_PAYLOAD, 'role': role})
        assert response.status_code == 422
    assert not keycloak.admin_users


def test_duplicate_username_is_a_conflict_and_keeps_existing_account(configured_client, keycloak):
    keycloak.add_admin_user(id='existing', email='existing@example.test', username='admin_1', roles=['crm-user'])
    login(configured_client, keycloak, roles=('crm-superadmin',))
    response = configured_client.post(USERS_PATH, json=CREATE_PAYLOAD)
    assert response.status_code == 409
    assert len(keycloak.admin_users) == 1


def test_failed_role_assignment_rolls_back_new_account(configured_client, keycloak, database_url):
    keycloak.fail_role_assignment = True
    login(configured_client, keycloak, roles=('crm-superadmin',))
    response = configured_client.post(USERS_PATH, json=CREATE_PAYLOAD)
    assert response.status_code == 503
    assert not keycloak.admin_users
    with database(database_url) as db:
        assert db.scalar(select(User).where(User.email == CREATE_PAYLOAD['email'])) is None


def test_superadmin_changes_existing_manager_to_admin_and_revokes_old_sessions(configured_client, keycloak, database_url):
    keycloak.add_admin_user(id='kc-manager', email='manager@example.test', username='manager', roles=['crm-user'])
    login(configured_client, keycloak, subject='kc-manager', email='manager@example.test')
    login(configured_client, keycloak, roles=('crm-admin', 'crm-superadmin'), subject='kc-irina', email='irina@example.test')

    response = configured_client.patch(f'{USERS_PATH}/kc-manager/role', json={'role': 'crm-admin'})

    assert response.status_code == 200, response.text
    assert response.json()['role'] == 'crm-admin'
    assert keycloak.admin_users['kc-manager']['roles'] == ['crm-admin']
    assert 'kc-manager' in keycloak.logged_out_users
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-manager'))
        assert user.roles == ['crm-admin']
        assert all(s.revoked_at is not None for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)))
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'admin.user_role_change'))
        assert event is not None and event.payload['new_role'] == 'crm-admin'


def test_superadmin_can_assign_admin_role_to_pending_account(configured_client, keycloak):
    keycloak.add_admin_user(id='kc-pending', email='pending@example.test', username='pending', roles=[])
    login(configured_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')

    response = configured_client.patch(f'{USERS_PATH}/kc-pending/role', json={'role': 'crm-admin'})

    assert response.status_code == 200, response.text
    assert keycloak.admin_users['kc-pending']['roles'] == ['crm-admin']
    assert [u['username'] for u in configured_client.get(USERS_PATH).json()['users']] == ['pending']
    assert configured_client.get(PENDING_PATH).json()['pending'] == []


def test_superadmins_grant_and_change_the_head_role_but_not_superadmin_through_it(configured_client, keycloak):
    # «Руководитель» is assigned in the CRM (29 Sep); superadmin rights have their own grant/revoke actions.
    keycloak.add_admin_user(id='kc-head', email='head@example.test', username='head', roles=['crm-supervisor'])
    keycloak.add_admin_user(id='kc-manager', email='manager@example.test', username='manager', roles=['crm-user'])
    keycloak.add_admin_user(id='kc-super', email='super@example.test', username='super2', roles=['crm-superadmin'])
    login(configured_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')

    assert configured_client.patch(f'{USERS_PATH}/kc-manager/role', json={'role': 'crm-supervisor'}).status_code == 200
    assert keycloak.admin_users['kc-manager']['roles'] == ['crm-supervisor']
    assert configured_client.patch(f'{USERS_PATH}/kc-head/role', json={'role': 'crm-user'}).status_code == 200
    assert keycloak.admin_users['kc-head']['roles'] == ['crm-user']
    assert configured_client.patch(f'{USERS_PATH}/kc-manager/role', json={'role': 'crm-superadmin'}).status_code == 422
    assert configured_client.patch(f'{USERS_PATH}/kc-super/role', json={'role': 'crm-user'}).status_code == 409
    assert keycloak.admin_users['kc-super']['roles'] == ['crm-superadmin']


def test_only_superadmin_can_change_role_or_reset_password(configured_client, keycloak):
    keycloak.add_admin_user(id='kc-target', email='target@example.test', username='target', roles=['crm-user'])
    login(configured_client, keycloak, roles=('crm-admin',), subject='kc-admin')

    assert configured_client.patch(f'{USERS_PATH}/kc-target/role', json={'role': 'crm-admin'}).status_code == 403
    assert configured_client.post(f'{USERS_PATH}/kc-target/reset-password').status_code == 403
    assert keycloak.admin_users['kc-target']['roles'] == ['crm-user']
    assert 'temporary_password' not in keycloak.admin_users['kc-target']


def test_password_reset_returns_one_time_secret_and_ends_existing_sessions(configured_client, keycloak, database_url):
    keycloak.add_admin_user(id='kc-target', email='target@example.test', username='target', roles=['crm-user'])
    login(configured_client, keycloak, subject='kc-target', email='target@example.test')
    login(configured_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')

    response = configured_client.post(f'{USERS_PATH}/kc-target/reset-password')

    assert response.status_code == 200, response.text
    secret = response.json()['temporary_password']
    assert len(secret) >= 24
    assert response.headers['cache-control'] == 'no-store'
    assert keycloak.admin_users['kc-target']['temporary_password'] == secret
    assert 'kc-target' in keycloak.logged_out_users
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-target'))
        assert all(s.revoked_at is not None for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)))
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'admin.user_password_reset'))
        assert event is not None and secret not in str(event.payload)


def test_reset_and_role_change_do_not_modify_unknown_keycloak_user(configured_client, keycloak):
    login(configured_client, keycloak, roles=('crm-superadmin', 'crm-admin'))
    assert configured_client.patch(f'{USERS_PATH}/unknown/role', json={'role': 'crm-admin'}).status_code == 404
    assert configured_client.post(f'{USERS_PATH}/unknown/reset-password').status_code == 404


def test_failed_old_role_removal_restores_original_access(configured_client, keycloak):
    keycloak.add_admin_user(id='kc-target', email='target@example.test', username='target', roles=['crm-admin'])
    login(configured_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')
    keycloak.fail_role_removal = True

    response = configured_client.patch(f'{USERS_PATH}/kc-target/role', json={'role': 'crm-user'})

    assert response.status_code == 503
    assert keycloak.admin_users['kc-target']['roles'] == ['crm-admin']
