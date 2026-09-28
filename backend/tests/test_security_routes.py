import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import User, UserSession, utcnow
from app.security import new_token, token_hash
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, finish_login, login, make_settings, start_login

BASE = '/api/v1/security'
CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'


@pytest.fixture
def kc_client(database_url, keycloak):
    app = create_app(make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                                   keycloak_admin_client_secret=ADMIN_CLIENT_SECRET,
                                   keycloak_admin_base_url=ADMIN_BASE_URL), http_client=keycloak.http_client())
    with TestClient(app) as test_client:
        yield test_client


def _sign_in(client, keycloak, sid='sid-current'):
    response = finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-anna',
                            name='Анна Петрова', email='anna@x.test', sid=sid)
    assert response.status_code == 302
    me = client.get('/api/v1/auth/me').json()
    client.headers['X-CSRF-Token'] = me['csrf_token']
    return me['user']


def _other_session(database_url, user_id, *, sid=None, ua=CHROME, ip='10.0.0.9', expired=False, revoked=False):
    now = utcnow()
    with database(database_url) as db:
        row = UserSession(id=token_hash(new_token()), user_id=user_id, csrf_token='x', created_at=now - timedelta(hours=2),
                          expires_at=now - timedelta(minutes=1) if expired else now + timedelta(hours=8),
                          validated_at=now - timedelta(minutes=5), ip=ip, user_agent=ua, keycloak_session_id=sid,
                          revoked_at=now if revoked else None)
        db.add(row)
        db.commit()
        return row.id


def _revoked(database_url, session_id):
    with database(database_url) as db:
        return db.get(UserSession, session_id).revoked_at is not None


def test_lists_only_own_live_sessions_without_secrets(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    other = _other_session(database_url, me['id'])
    _other_session(database_url, me['id'], expired=True)
    _other_session(database_url, me['id'], revoked=True)
    stranger = User(keycloak_sub='kc-x', email='x@x.test', full_name='Чужой', roles=['crm-user'])
    with database(database_url) as db:
        db.add(stranger)
        db.commit()
        _other_session(database_url, stranger.id)
    response = kc_client.get(f'{BASE}/sessions')
    body = response.json()
    assert len(body) == 2 and sum(s['current'] for s in body) == 1
    other_row = next(s for s in body if not s['current'])
    assert other_row['device'] == 'Chrome · Windows' and other_row['ip'] == '10.0.0.9'
    assert other not in response.text and 'csrf' not in response.text.lower() and 'sid-current' not in response.text


def test_ending_another_session_ends_it_in_keycloak_too(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    keycloak.admin_sessions = {'sid-current', 'sid-laptop'}
    other = _other_session(database_url, me['id'], sid='sid-laptop')
    public_id = next(s['id'] for s in kc_client.get(f'{BASE}/sessions').json() if not s['current'])
    response = kc_client.delete(f'{BASE}/sessions/{public_id}')
    assert response.status_code == 200, response.text
    assert response.json()['keycloak_ended'] is True
    assert _revoked(database_url, other) and keycloak.admin_sessions == {'sid-current'}


def test_a_session_sharing_the_current_devices_keycloak_session_is_ended_only_in_the_crm(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    keycloak.admin_sessions = {'sid-current'}
    other = _other_session(database_url, me['id'], sid='sid-current')
    public_id = next(s['id'] for s in kc_client.get(f'{BASE}/sessions').json() if not s['current'])
    body = kc_client.delete(f'{BASE}/sessions/{public_id}').json()
    assert _revoked(database_url, other) and keycloak.admin_sessions == {'sid-current'}
    assert body['keycloak_ended'] is False
    assert 'общий с этим устройством' in body['message'] and '30 минут' not in body['message']


def test_keycloak_failure_still_ends_the_crm_session_honestly(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    keycloak.fail_session_delete = True
    other = _other_session(database_url, me['id'], sid='sid-laptop')
    public_id = next(s['id'] for s in kc_client.get(f'{BASE}/sessions').json() if not s['current'])
    body = kc_client.delete(f'{BASE}/sessions/{public_id}').json()
    assert _revoked(database_url, other) and body['keycloak_ended'] is False
    assert '30 минут' in body['message']


def test_current_foreign_and_unknown_sessions_cannot_be_ended(kc_client, keycloak, database_url):
    _sign_in(kc_client, keycloak)
    current = next(s['id'] for s in kc_client.get(f'{BASE}/sessions').json() if s['current'])
    assert kc_client.delete(f'{BASE}/sessions/{current}').status_code == 409
    assert kc_client.delete(f'{BASE}/sessions/0000000000000000').status_code == 404


def test_terminate_others_keeps_the_current_session(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    keycloak.admin_sessions = {'sid-current', 'sid-a', 'sid-b'}
    a, b = _other_session(database_url, me['id'], sid='sid-a'), _other_session(database_url, me['id'], sid='sid-b')
    body = kc_client.post(f'{BASE}/sessions/terminate-others').json()
    assert body['count'] == 2 and _revoked(database_url, a) and _revoked(database_url, b)
    assert keycloak.admin_sessions == {'sid-current'}
    assert [s['current'] for s in kc_client.get(f'{BASE}/sessions').json()] == [True]


def test_old_session_without_sid_is_ended_only_in_the_crm(client, keycloak, database_url):
    me = login(client, keycloak)
    other = _other_session(database_url, me['user']['id'])
    public_id = next(s['id'] for s in client.get(f'{BASE}/sessions').json() if not s['current'])
    body = client.delete(f'{BASE}/sessions/{public_id}').json()
    assert _revoked(database_url, other) and body['keycloak_ended'] is False


def test_login_history_crm_part_and_keycloak_disabled(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    _other_session(database_url, me['id'], revoked=True)
    body = kc_client.get(f'{BASE}/login-history').json()
    assert {e['state'] for e in body['crm']} == {'active', 'ended'}
    assert body['keycloak'] == {'available': False, 'reason': 'disabled', 'events': []}


def test_login_history_keycloak_events_when_enabled(kc_client, keycloak, database_url):
    _sign_in(kc_client, keycloak)
    keycloak.realm_events_enabled = True
    keycloak.admin_events = [
        {'time': 1790000000000, 'type': 'LOGIN_ERROR', 'userId': 'kc-anna', 'ipAddress': '10.0.0.2', 'error': 'invalid_user_credentials'},
        {'time': 1790000100000, 'type': 'LOGIN', 'userId': 'kc-anna', 'ipAddress': '10.0.0.1'},
        {'time': 1790000200000, 'type': 'LOGIN', 'userId': 'someone-else', 'ipAddress': '10.0.0.3'},
    ]
    keycloak_part = kc_client.get(f'{BASE}/login-history').json()['keycloak']
    assert keycloak_part['available'] is True
    assert [(e['type'], e['label'], e['ip']) for e in keycloak_part['events']] == [  # newest first
        ('LOGIN', 'Вход', '10.0.0.1'), ('LOGIN_ERROR', 'Неудачная попытка входа', '10.0.0.2')]


def test_login_history_without_keycloak_admin_or_permission(client, kc_client, keycloak, database_url):
    login(client, keycloak)
    assert client.get(f'{BASE}/login-history').json()['keycloak']['reason'] == 'not_configured'
    _sign_in(kc_client, keycloak)
    keycloak.realm_events_enabled = True
    keycloak.events_forbidden = True
    assert kc_client.get(f'{BASE}/login-history').json()['keycloak']['reason'] == 'disabled'
    keycloak.events_forbidden = False
    keycloak.unavailable = True
    part = kc_client.get(f'{BASE}/login-history')
    keycloak.unavailable = False
    assert part.json()['keycloak']['reason'] == 'unavailable'


def test_password_policy_for_a_user_and_for_an_admin(kc_client, keycloak, database_url):
    _sign_in(kc_client, keycloak)
    body = kc_client.get(f'{BASE}/password-policy').json()
    assert body['available'] is True and 'Не короче 12 символов' in body['rules']
    assert body['brute_force'] == 'После 30 неудачных попыток вход временно блокируется'
    assert body['change_password_url'].endswith('/realms/edu-crm/account/account-security/signing-in')
    assert body['admin_console_url'] is None
    kc_client.cookies.clear()
    kc_client.headers.pop('X-CSRF-Token', None)
    login(kc_client, keycloak, roles=('crm-admin',), subject='kc-adm', name='Админ Системы')
    admin = kc_client.get(f'{BASE}/password-policy').json()
    assert admin['admin_console_url'].endswith('/admin/master/console/#/edu-crm/authentication/policies')


def test_password_policy_unavailable_without_keycloak_admin(client, keycloak):
    login(client, keycloak)
    body = client.get(f'{BASE}/password-policy').json()
    assert body['available'] is False and body['rules'] == []


def test_terminate_others_stops_calling_an_unavailable_keycloak(kc_client, keycloak, database_url):
    me = _sign_in(kc_client, keycloak)
    keycloak.fail_session_delete = True
    ids = [_other_session(database_url, me['id'], sid=f'sid-{i}') for i in range(3)]
    body = kc_client.post(f'{BASE}/sessions/terminate-others').json()
    assert body['count'] == 3 and all(_revoked(database_url, i) for i in ids)
    assert keycloak.session_delete_calls == 1  # the first failure stops further Keycloak calls
    assert '30 минут' in body['message']
