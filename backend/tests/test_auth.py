from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth import LOGIN_COOKIE, SESSION_COOKIE, _revalidate
from app.models import LoginState, User, UserSession, utcnow
from app.security import token_hash
from fake_keycloak import CLIENT_ID, ISSUER
from helpers import database, finish_login, login, make_sessions_stale, start_login


def test_login_redirects_to_keycloak_with_pkce_and_stores_only_hashes(client, database_url):
    query = start_login(client, '/interactions')
    assert query['client_id'] == CLIENT_ID
    assert query['code_challenge_method'] == 'S256'
    assert query['redirect_uri'] == 'http://testserver/api/v1/auth/callback'
    browser_value = client.cookies.get(LOGIN_COOKIE)
    assert browser_value
    with database(database_url) as db:
        states = db.scalars(select(LoginState)).all()
    assert len(states) == 1
    assert states[0].state_hash != query['state']
    assert states[0].browser_hash == token_hash(browser_value)
    assert states[0].next_path == '/interactions'


def test_successful_login_sets_protected_cookie_and_returns_user(client, keycloak, database_url):
    response = finish_login(client, keycloak, start_login(client, '/tasks'), roles=('crm-supervisor', 'crm-user'))
    assert response.status_code == 302
    assert response.headers['location'] == '/tasks'
    session_cookie = next(value for value in response.headers.get_list('set-cookie') if value.startswith(f'{SESSION_COOKIE}='))
    assert 'httponly' in session_cookie.lower()
    assert 'samesite=lax' in session_cookie.lower()
    assert LOGIN_COOKIE not in client.cookies

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


def test_callback_planted_in_another_browser_is_rejected(app, keycloak):
    with TestClient(app) as attacker, TestClient(app) as victim:
        query = start_login(attacker)
        code = keycloak.issue_code(nonce=query['nonce'], code_challenge=query['code_challenge'], subject='kc-attacker')
        planted = victim.get('/api/v1/auth/callback', params={'code': code, 'state': query['state']}, follow_redirects=False)
        assert planted.headers['location'] == '/?auth_error=LOGIN_EXPIRED'
        assert victim.get('/api/v1/auth/me').status_code == 401
        # The rejected attempt did not consume the state: the browser that started the login can still finish it.
        own = attacker.get('/api/v1/auth/callback', params={'code': code, 'state': query['state']}, follow_redirects=False)
        assert own.headers['location'] == '/'


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


def test_too_many_pending_logins_are_limited(client, monkeypatch):
    monkeypatch.setattr('app.auth.MAX_PENDING_LOGINS', 2)
    start_login(client)
    start_login(client)
    response = client.get('/api/v1/auth/login', follow_redirects=False)
    assert response.status_code == 429
    assert response.json()['code'] == 'RATE_LIMITED'


def test_repeat_login_updates_the_same_user(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',), name='Анна Демо')
    login(client, keycloak, roles=('crm-admin',), name='Анна Демо-Иванова')
    with database(database_url) as db:
        [user] = db.scalars(select(User)).all()
    assert user.full_name == 'Анна Демо-Иванова'
    assert user.roles == ['crm-admin']


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

    missing = client.post('/api/v1/universities', json=payload)
    assert missing.status_code == 403
    assert missing.json()['code'] == 'CSRF_INVALID'
    assert client.post('/api/v1/universities', json=payload, headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    for origin in ('http://evil.example', 'null'):
        foreign = client.post('/api/v1/universities', json=payload, headers={'X-CSRF-Token': token, 'Origin': origin})
        assert foreign.status_code == 403
        assert foreign.json()['code'] == 'CSRF_INVALID'
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


def test_revalidation_rereads_a_session_refreshed_by_a_concurrent_request(app, client, keycloak, database_url):
    login(client, keycloak)
    make_sessions_stale(database_url)
    session_id = token_hash(client.cookies.get(SESSION_COOKIE))
    with app.state.session_factory() as db:
        # This request loaded the session while it was still stale...
        stale = db.get(UserSession, session_id)
        assert (utcnow() - stale.validated_at).total_seconds() > 120
        # ...then a concurrent request refreshed it, rotating the single-use refresh token.
        assert client.get('/api/v1/auth/me').status_code == 200
        requests_before = len(keycloak.token_requests)

        session, _ = _revalidate(SimpleNamespace(app=app), db, session_id, utcnow())

        assert len(keycloak.token_requests) == requests_before
        assert session.revoked_at is None
    assert client.get('/api/v1/auth/me').status_code == 200


def test_keycloak_outage_returns_503_and_keeps_the_session(client, keycloak, database_url):
    login(client, keycloak)
    make_sessions_stale(database_url)
    keycloak.unavailable = True
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 503
    assert response.json()['code'] == 'SERVICE_UNAVAILABLE'
    with database(database_url) as db:
        assert db.scalars(select(UserSession)).one().revoked_at is None
    keycloak.unavailable = False
    assert client.get('/api/v1/auth/me').status_code == 200


def test_failed_revalidation_revokes_session(client, keycloak, database_url):
    login(client, keycloak)
    keycloak.fail_refresh = True
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').status_code == 401
    keycloak.fail_refresh = False
    assert client.get('/api/v1/auth/me').status_code == 401
    with database(database_url) as db:
        assert db.scalars(select(UserSession)).one().revoked_at is not None


def test_refresh_without_id_token_revokes_session(client, keycloak, database_url):
    login(client, keycloak)
    keycloak.omit_id_token_on_refresh = True
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').status_code == 401


def test_losing_all_crm_roles_revokes_session(client, keycloak, database_url):
    login(client, keycloak)
    keycloak.set_roles('kc-user-1', ['offline_access'])
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').status_code == 401


def test_logout_ends_keycloak_session_and_revokes_crm_session(client, keycloak, database_url):
    login(client, keycloak)
    response = client.post('/api/v1/auth/logout')
    assert response.status_code == 200
    assert response.json()['logout_url'] == 'http://testserver/'
    assert len(keycloak.logouts) == 1
    with database(database_url) as db:
        assert db.scalars(select(UserSession)).one().revoked_at is not None
    assert client.get('/api/v1/auth/me').status_code == 401


def test_logout_while_keycloak_is_down_still_signs_out(client, keycloak, database_url):
    login(client, keycloak)
    make_sessions_stale(database_url)
    keycloak.unavailable = True
    response = client.post('/api/v1/auth/logout')
    assert response.status_code == 200
    parts = urlsplit(response.json()['logout_url'])
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == f'{ISSUER}/protocol/openid-connect/logout'
    assert {key: values[0] for key, values in parse_qs(parts.query).items()} == {'client_id': CLIENT_ID, 'post_logout_redirect_uri': 'http://testserver/'}
    with database(database_url) as db:
        assert db.scalars(select(UserSession)).one().revoked_at is not None


def test_logout_requires_csrf_token(client, keycloak):
    login(client, keycloak)
    client.headers.pop('X-CSRF-Token')
    response = client.post('/api/v1/auth/logout')
    assert response.status_code == 403
    assert response.json()['code'] == 'CSRF_INVALID'
