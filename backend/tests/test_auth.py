from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select, update

from app.auth import SESSION_COOKIE
from app.models import LoginState, User, UserSession, utcnow
from fake_keycloak import CLIENT_ID, ISSUER
from helpers import database, finish_login, login, make_sessions_stale, start_login


def test_login_redirects_to_keycloak_with_pkce_and_stores_only_a_hash(client, database_url):
    query = start_login(client, '/interactions')
    assert query['client_id'] == CLIENT_ID
    assert query['code_challenge_method'] == 'S256'
    assert query['redirect_uri'] == 'http://testserver/api/v1/auth/callback'
    with database(database_url) as db:
        states = db.scalars(select(LoginState)).all()
    assert len(states) == 1
    assert states[0].state_hash != query['state']
    assert states[0].next_path == '/interactions'


def test_successful_login_sets_protected_cookie_and_returns_user(client, keycloak, database_url):
    response = finish_login(client, keycloak, start_login(client, '/tasks'), roles=('crm-supervisor', 'crm-user'))
    assert response.status_code == 302
    assert response.headers['location'] == '/tasks'
    cookie = response.headers['set-cookie']
    assert f'{SESSION_COOKIE}=' in cookie
    assert 'httponly' in cookie.lower()
    assert 'samesite=lax' in cookie.lower()

    me = client.get('/api/v1/auth/me').json()
    assert me['user']['full_name'] == 'Анна Демо'
    assert me['user']['roles'] == ['crm-supervisor', 'crm-user']
    assert me['csrf_token']

    raw_cookie = client.cookies.get(SESSION_COOKIE)
    with database(database_url) as db:
        session = db.scalars(select(UserSession)).one()
        assert session.id != raw_cookie
        for refresh_token in keycloak.refresh_tokens:
            assert refresh_token not in session.refresh_token_encrypted


def test_state_cannot_be_replayed(client, keycloak):
    query = start_login(client)
    assert finish_login(client, keycloak, query).headers['location'] == '/'
    assert finish_login(client, keycloak, query).headers['location'] == '/?auth_error=LOGIN_EXPIRED'


def test_expired_state_is_rejected(client, keycloak, database_url):
    query = start_login(client)
    with database(database_url) as db:
        db.execute(update(LoginState).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    assert finish_login(client, keycloak, query).headers['location'] == '/?auth_error=LOGIN_EXPIRED'


def test_nonce_mismatch_fails(client, keycloak):
    query = start_login(client)
    code = keycloak.issue_code(nonce='a-different-nonce', code_challenge=query['code_challenge'])
    response = client.get('/api/v1/auth/callback', params={'code': code, 'state': query['state']}, follow_redirects=False)
    assert response.headers['location'] == '/?auth_error=LOGIN_FAILED'
    assert client.get('/api/v1/auth/me').status_code == 401


def test_wrong_pkce_verifier_fails(client, keycloak):
    query = start_login(client)
    code = keycloak.issue_code(nonce=query['nonce'], code_challenge='not-the-challenge')
    response = client.get('/api/v1/auth/callback', params={'code': code, 'state': query['state']}, follow_redirects=False)
    assert response.headers['location'] == '/?auth_error=LOGIN_FAILED'


def test_user_without_crm_roles_gets_no_session(client, keycloak):
    response = finish_login(client, keycloak, start_login(client), roles=('offline_access',))
    assert response.headers['location'] == '/?auth_error=NO_ACCESS'
    assert SESSION_COOKIE not in client.cookies
    assert client.get('/api/v1/auth/me').status_code == 401


def test_cancelled_login(client):
    response = client.get('/api/v1/auth/callback', params={'error': 'access_denied'}, follow_redirects=False)
    assert response.headers['location'] == '/?auth_error=LOGIN_CANCELLED'


def test_open_redirect_is_blocked(client, keycloak):
    response = finish_login(client, keycloak, start_login(client, '//evil.example/steal'))
    assert response.headers['location'] == '/'


def test_protected_endpoint_requires_login(client):
    response = client.get('/api/v1/launches')
    assert response.status_code == 401
    assert response.json()['code'] == 'UNAUTHENTICATED'


def test_expired_session_is_rejected(client, keycloak, database_url):
    login(client, keycloak)
    with database(database_url) as db:
        db.execute(update(UserSession).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    assert client.get('/api/v1/auth/me').status_code == 401


def test_deactivated_user_loses_session_and_cannot_log_in(client, keycloak, database_url):
    login(client, keycloak)
    with database(database_url) as db:
        db.execute(update(User).values(is_active=False))
        db.commit()
    assert client.get('/api/v1/auth/me').status_code == 401
    assert finish_login(client, keycloak, start_login(client)).headers['location'] == '/?auth_error=NO_ACCESS'


def test_mutations_require_csrf_token_and_trusted_origin(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    token = client.headers.pop('X-CSRF-Token')
    payload = {'name': 'Вуз', 'city': 'Москва'}

    assert client.post('/api/v1/universities', json=payload).status_code == 403
    assert client.post('/api/v1/universities', json=payload, headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    foreign = client.post('/api/v1/universities', json=payload, headers={'X-CSRF-Token': token, 'Origin': 'http://evil.example'})
    assert foreign.status_code == 403
    assert foreign.json()['code'] == 'FORBIDDEN'
    trusted = client.post('/api/v1/universities', json=payload, headers={'X-CSRF-Token': token, 'Origin': 'http://testserver'})
    assert trusted.status_code == 201


def test_fresh_session_is_not_revalidated(client, keycloak):
    login(client, keycloak)
    requests_before = len(keycloak.token_requests)
    assert client.get('/api/v1/auth/me').status_code == 200
    assert len(keycloak.token_requests) == requests_before


def test_revalidation_picks_up_role_changes(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    keycloak.set_roles('kc-user-1', ['crm-admin'])
    make_sessions_stale(database_url)
    me = client.get('/api/v1/auth/me').json()
    assert me['user']['roles'] == ['crm-admin']
    assert keycloak.token_requests[-1]['grant_type'] == 'refresh_token'


def test_failed_revalidation_revokes_session(client, keycloak, database_url):
    login(client, keycloak)
    keycloak.fail_refresh = True
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').status_code == 401
    keycloak.fail_refresh = False
    assert client.get('/api/v1/auth/me').status_code == 401
    with database(database_url) as db:
        assert db.scalars(select(UserSession)).one().revoked_at is not None


def test_losing_all_crm_roles_revokes_session(client, keycloak, database_url):
    login(client, keycloak)
    keycloak.set_roles('kc-user-1', ['offline_access'])
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').status_code == 401


def test_logout_revokes_session_and_returns_keycloak_logout_url(client, keycloak, database_url):
    login(client, keycloak)
    response = client.post('/api/v1/auth/logout')
    assert response.status_code == 200
    parts = urlsplit(response.json()['logout_url'])
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == f'{ISSUER}/protocol/openid-connect/logout'
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert query == {'client_id': CLIENT_ID, 'post_logout_redirect_uri': 'http://testserver/'}
    with database(database_url) as db:
        assert db.scalars(select(UserSession)).one().revoked_at is not None
    assert client.get('/api/v1/auth/me').status_code == 401


def test_logout_requires_csrf_token(client, keycloak):
    login(client, keycloak)
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/v1/auth/logout').status_code == 403
