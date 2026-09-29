"""Password setup for people who signed up (owner decision 2026-09-29, option 1): Keycloak asks for the password only
after the e-mail link, so someone granted access may still have no password. Granting access then e-mails them a
Keycloak link to confirm the address and set a password (valid 12 hours); the superadmin can send it again."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, login, make_settings

USERS = '/api/v1/admin/users'
TWELVE_HOURS = '43200'


@pytest.fixture
def client(database_url, keycloak):
    app = create_app(
        make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                      keycloak_admin_client_secret=ADMIN_CLIENT_SECRET, keycloak_admin_base_url=ADMIN_BASE_URL),
        http_client=keycloak.http_client(),
    )
    with TestClient(app) as test_client:
        login(test_client, keycloak, roles=('crm-superadmin', 'crm-admin'), subject='kc-irina')
        yield test_client


def _unfinished(keycloak, id='kc-new'):
    keycloak.add_admin_user(id=id, email='ivanov@edu.hse.ru', username='ivanov', roles=[], email_verified=False,
                            required_actions=['VERIFY_EMAIL', 'UPDATE_PASSWORD'])


def test_granting_access_emails_a_password_setup_link(client, keycloak, database_url):
    _unfinished(keycloak)
    response = client.patch(f'{USERS}/kc-new/role', json={'role': 'crm-user'})
    assert response.status_code == 200, response.text
    assert response.json()['password_setup'] == 'sent'
    assert keycloak.actions_emails == [('kc-new', ['VERIFY_EMAIL', 'UPDATE_PASSWORD'], TWELVE_HOURS)]
    with database(database_url) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'admin.password_setup_email'))
        assert (event.entity_type, event.entity_id) == ('keycloak_user', 'kc-new')


def test_someone_who_finished_setup_gets_no_email(client, keycloak):
    keycloak.add_admin_user(id='kc-done', email='done@mail.ru', username='done', roles=[])
    response = client.patch(f'{USERS}/kc-done/role', json={'role': 'crm-user'})
    assert response.json()['password_setup'] == 'not_needed'
    assert keycloak.actions_emails == []


def test_only_the_missing_steps_are_asked_for(client, keycloak):
    keycloak.add_admin_user(id='kc-half', email='half@mail.ru', username='half', roles=[], required_actions=['UPDATE_PASSWORD'])
    client.patch(f'{USERS}/kc-half/role', json={'role': 'crm-user'})
    assert keycloak.actions_emails == [('kc-half', ['UPDATE_PASSWORD'], TWELVE_HOURS)]


def test_changing_an_existing_role_sends_nothing(client, keycloak):
    keycloak.add_admin_user(id='kc-kam', email='kam@mail.ru', username='kam', roles=['crm-user'],
                            required_actions=['UPDATE_PASSWORD'])
    response = client.patch(f'{USERS}/kc-kam/role', json={'role': 'crm-admin'})
    assert response.json()['password_setup'] == 'not_needed'
    assert keycloak.actions_emails == []


def test_a_failed_email_keeps_the_access_and_says_so(client, keycloak):
    _unfinished(keycloak)
    keycloak.fail_actions_email = True
    response = client.patch(f'{USERS}/kc-new/role', json={'role': 'crm-user'})
    assert response.status_code == 200
    assert response.json()['password_setup'] == 'failed'
    assert keycloak.admin_users['kc-new']['roles'] == ['crm-user']


def test_the_users_list_marks_unfinished_setup(client, keycloak):
    _unfinished(keycloak)
    keycloak.add_admin_user(id='kc-done', email='done@mail.ru', username='done', roles=['crm-user'])
    client.patch(f'{USERS}/kc-new/role', json={'role': 'crm-user'})
    pending = {u['username']: u['setup_pending'] for u in client.get(USERS).json()['users']}
    assert pending == {'ivanov': True, 'done': False}


def test_the_superadmin_can_send_the_link_again(client, keycloak, database_url):
    _unfinished(keycloak)
    keycloak.admin_users['kc-new']['roles'] = ['crm-user']
    response = client.post(f'{USERS}/kc-new/password-setup-email')
    assert response.status_code == 200, response.text
    assert response.json() == {'sent': True, 'message': 'Письмо для установки пароля отправлено на ivanov@edu.hse.ru.'}
    assert keycloak.actions_emails == [('kc-new', ['VERIFY_EMAIL', 'UPDATE_PASSWORD'], TWELVE_HOURS)]


def test_sending_again_is_refused_when_setup_is_finished(client, keycloak):
    keycloak.add_admin_user(id='kc-done', email='done@mail.ru', username='done', roles=['crm-user'])
    response = client.post(f'{USERS}/kc-done/password-setup-email')
    assert response.status_code == 409
    assert keycloak.actions_emails == []


def test_sending_again_reports_a_mail_failure(client, keycloak):
    _unfinished(keycloak)
    keycloak.fail_actions_email = True
    assert client.post(f'{USERS}/kc-new/password-setup-email').status_code == 503


def test_only_the_superadmin_can_send_it(database_url, keycloak):
    app = create_app(make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                                   keycloak_admin_client_secret=ADMIN_CLIENT_SECRET, keycloak_admin_base_url=ADMIN_BASE_URL),
                     http_client=keycloak.http_client())
    _unfinished(keycloak)
    with TestClient(app) as other:
        login(other, keycloak, roles=('crm-admin',), subject='kc-admin')
        assert other.post(f'{USERS}/kc-new/password-setup-email').status_code == 403
    assert keycloak.actions_emails == []
