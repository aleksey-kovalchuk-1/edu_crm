import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent, Launch, User
from app.plan_routes import resolve_assignee
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, login, make_settings
from test_reports import create_launch, create_university

PROFILE = '/api/v1/profile'


@pytest.fixture
def kc_client(database_url, keycloak):
    app = create_app(make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                                   keycloak_admin_client_secret=ADMIN_CLIENT_SECRET,
                                   keycloak_admin_base_url=ADMIN_BASE_URL), http_client=keycloak.http_client())
    with TestClient(app) as test_client:
        yield test_client


def _login_irina(client, keycloak):
    keycloak.add_admin_user(id='kc-irina', email='irina@x.test', username='irina', roles=['crm-admin'],
                            first_name='Ирина', last_name='Петрова')
    return login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова', email='irina@x.test')


def test_get_profile_defaults(kc_client, keycloak):
    _login_irina(kc_client, keycloak)
    body = kc_client.get(PROFILE).json()
    assert body['full_name'] == 'Ирина Петрова' and body['timezone'] == 'Europe/Moscow'
    assert (body['telegram'], body['whatsapp'], body['middle_name']) == ('', '', '')
    assert body['email_sender_identity_id'] is None and body['phone_verified_at'] is None
    # Names not yet mirrored locally fall back to splitting full_name once.
    assert (body['first_name'], body['last_name']) == ('Ирина', 'Петрова')


def test_patch_contacts_and_timezone_without_keycloak_admin(client, keycloak, database_url):
    login(client, keycloak)
    response = client.patch(PROFILE, json={
        'timezone': 'Asia/Yekaterinburg', 'telegram': '@anna_demo', 'whatsapp': '8 (999) 123-45-67',
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body['timezone'], body['telegram'], body['whatsapp']) == ('Asia/Yekaterinburg', 'anna_demo', '+79991234567')
    with database(database_url) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'profile.update'))
        assert event.payload == {'fields': ['timezone', 'telegram', 'whatsapp']}  # names only, never values


@pytest.mark.parametrize('payload,field', [
    ({'timezone': 'Mars/Olympus'}, 'timezone'),
    ({'timezone': ''}, 'timezone'),
    ({'telegram': 'ab'}, 'telegram'),
    ({'telegram': 'bad name!'}, 'telegram'),
    ({'whatsapp': '12'}, 'whatsapp'),
    ({'first_name': '   '}, 'first_name'),
    ({'middle_name': 'x' * 101}, 'middle_name'),
    ({'phone': '+79991234567'}, 'phone'),
])
def test_patch_rejects_invalid_values(client, keycloak, payload, field):
    login(client, keycloak)
    response = client.patch(PROFILE, json=payload)
    assert response.status_code == 422, response.text
    assert any(d['field'] == field for d in response.json()['details'])


def test_empty_contacts_clear_them(client, keycloak):
    login(client, keycloak)
    client.patch(PROFILE, json={'telegram': 'anna_demo', 'whatsapp': '+79991234567'})
    body = client.patch(PROFILE, json={'telegram': '', 'whatsapp': ''}).json()
    assert (body['telegram'], body['whatsapp']) == ('', '')


def test_rename_writes_keycloak_then_cascades(kc_client, keycloak, database_url):
    me = _login_irina(kc_client, keycloak)
    university = create_university(kc_client, 'Вуз профиля')
    launch_id = create_launch(kc_client, university['id'], owner='Ирина Петрова')['id']
    response = kc_client.patch(PROFILE, json={'first_name': 'Ирина', 'last_name': 'Смирнова'})
    assert response.status_code == 200, response.text
    assert response.json()['full_name'] == 'Ирина Смирнова'
    assert keycloak.admin_users['kc-irina']['lastName'] == 'Смирнова'
    with database(database_url) as db:
        launch = db.get(Launch, launch_id)
        assert launch.owner == 'Ирина Смирнова'
        assert resolve_assignee(db, {'assignee_rule': 'interaction_owner'}, university['id'], launch, None) == (me['user']['id'], None)
    options = kc_client.get('/api/v1/reports/options').json()['owners']
    assert 'Ирина Смирнова' in options and 'Ирина Петрова' not in options
    report = kc_client.get('/api/v1/reports/interactions', params={'owner': 'Ирина Смирнова'})
    assert report.status_code == 200, report.text
    assert report.json()['total'] == 1


def test_middle_name_goes_to_keycloak_without_cascade(kc_client, keycloak, database_url):
    _login_irina(kc_client, keycloak)
    response = kc_client.patch(PROFILE, json={'middle_name': 'Сергеевна'})
    assert response.status_code == 200, response.text
    assert response.json()['middle_name'] == 'Сергеевна' and response.json()['full_name'] == 'Ирина Петрова'
    assert keycloak.admin_users['kc-irina']['attributes']['middleName'] == ['Сергеевна']
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'user.renamed')) is None


def test_new_launch_with_new_name_links(kc_client, keycloak):
    me = _login_irina(kc_client, keycloak)
    kc_client.patch(PROFILE, json={'first_name': 'Ирина', 'last_name': 'Смирнова'})
    university = create_university(kc_client, 'Вуз после переименования')
    assert create_launch(kc_client, university['id'], owner='Ирина Смирнова')['owner_user_id'] == me['user']['id']


def test_keycloak_failure_changes_nothing(kc_client, keycloak, database_url):
    _login_irina(kc_client, keycloak)
    university = create_university(kc_client, 'Вуз отказа')
    launch_id = create_launch(kc_client, university['id'], owner='Ирина Петрова')['id']
    keycloak.unavailable = True
    response = kc_client.patch(PROFILE, json={'first_name': 'Ирина', 'last_name': 'Смирнова', 'timezone': 'Asia/Omsk'})
    keycloak.unavailable = False
    assert response.status_code == 503
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-irina'))
        assert user.full_name == 'Ирина Петрова' and user.timezone == 'Europe/Moscow'
        assert db.get(Launch, launch_id).owner == 'Ирина Петрова'


def test_rename_without_keycloak_admin_is_unavailable(client, keycloak):
    login(client, keycloak)
    assert client.patch(PROFILE, json={'first_name': 'Новое', 'last_name': 'Имя'}).status_code == 503


def test_duplicate_name_of_another_active_user_is_rejected(kc_client, keycloak, database_url):
    with database(database_url) as db:
        db.add(User(keycloak_sub='kc-other', email='o@x.test', full_name='Анна Смирнова', roles=['crm-user'], is_active=True))
        db.commit()
    _login_irina(kc_client, keycloak)
    response = kc_client.patch(PROFILE, json={'first_name': 'анна', 'last_name': 'смирнова '})
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'first_name'
    assert keycloak.admin_users['kc-irina']['lastName'] == 'Петрова'


def test_own_name_in_other_case_is_not_a_conflict(kc_client, keycloak):
    _login_irina(kc_client, keycloak)
    response = kc_client.patch(PROFILE, json={'first_name': 'ирина', 'last_name': 'петрова'})
    assert response.status_code == 200, response.text


def test_me_exposes_profile_fields(client, keycloak):
    login(client, keycloak)
    user = client.get('/api/v1/auth/me').json()['user']
    assert {'first_name', 'middle_name', 'last_name', 'timezone', 'telegram', 'whatsapp', 'phone_verified_at'} <= user.keys()


FULL_FORM = {'first_name': 'admin', 'middle_name': '', 'last_name': '', 'timezone': 'Asia/Omsk', 'telegram': '', 'whatsapp': ''}


def test_single_word_name_user_can_save_the_real_form_body(client, keycloak):
    # The form sends every field; a one-word full_name gives an empty last_name that must not block saving.
    login(client, keycloak, name='admin')
    response = client.patch(PROFILE, json=FULL_FORM)
    assert response.status_code == 200, response.text
    assert response.json()['timezone'] == 'Asia/Omsk'


def test_clearing_a_name_is_rejected_in_russian(kc_client, keycloak):
    _login_irina(kc_client, keycloak)
    response = kc_client.patch(PROFILE, json={'first_name': '', 'last_name': 'Петрова'})
    assert response.status_code == 422
    detail = response.json()['details'][0]
    assert detail['field'] == 'first_name' and detail['message'] == 'Укажите имя'


def test_profile_length_error_is_russian(client, keycloak):
    login(client, keycloak)
    detail = client.patch(PROFILE, json={'middle_name': 'x' * 101}).json()['details'][0]
    assert detail == {'field': 'middle_name', 'message': 'Не более 100 символов', 'type': 'string_too_long'}
