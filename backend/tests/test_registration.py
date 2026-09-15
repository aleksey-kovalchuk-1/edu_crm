"""GET /api/v1/auth/register (T-084): same PKCE/state/CSRF-safety machinery as /login (D-134/D-135),
the only difference is which Keycloak page it opens first. Keycloak itself is the authority that enforces
the .ru email pattern, CAPTCHA and email verification before any code ever reaches /callback (D-155-D-158);
those are verified against the real dev stack (see docs/night-report.md), not against fake_keycloak here.
"""
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from app.auth import LOGIN_COOKIE
from app.models import LoginState
from app.security import token_hash
from fake_keycloak import CLIENT_ID, ISSUER
from helpers import database, finish_login


def start_registration(client, next_path='/'):
    response = client.get('/api/v1/auth/register', params={'next': next_path}, follow_redirects=False)
    assert response.status_code == 302, response.text
    location = response.headers['location']
    return location, {key: values[0] for key, values in parse_qs(urlsplit(location).query).items()}


def test_register_redirects_to_keycloak_registrations_endpoint_with_pkce(client, database_url):
    location, query = start_registration(client, '/interactions')
    assert location.startswith(f'{ISSUER}/protocol/openid-connect/registrations?')
    assert query['client_id'] == CLIENT_ID
    assert query['code_challenge_method'] == 'S256'
    assert query['redirect_uri'] == 'http://testserver/api/v1/auth/callback'
    browser_value = client.cookies.get(LOGIN_COOKIE)
    assert browser_value
    with database(database_url) as db:
        states = db.scalars(select(LoginState)).all()
    assert len(states) == 1
    assert states[0].browser_hash == token_hash(browser_value)
    assert states[0].next_path == '/interactions'


def test_register_uses_a_different_endpoint_than_login_but_the_same_callback(client):
    _, login_query = (lambda r: (r, {key: values[0] for key, values in parse_qs(urlsplit(r.headers['location']).query).items()}))(
        client.get('/api/v1/auth/login', params={'next': '/'}, follow_redirects=False)
    )
    assert login_query['redirect_uri'] == 'http://testserver/api/v1/auth/callback'


def test_registration_state_completes_login_like_a_normal_one(client, keycloak, database_url):
    # Once Keycloak redirects back to /callback with a code, registration and login are indistinguishable:
    # the same state/PKCE/nonce checks and the same session issuance apply (fake_keycloak stands in for
    # Keycloak's own token endpoint here; the .ru/CAPTCHA/verify-email gates that happen before this point
    # are Keycloak-side and verified separately against the real stack).
    _, query = start_registration(client, '/tasks')
    response = finish_login(client, keycloak, query, roles=('crm-user',))
    assert response.status_code == 302
    assert response.headers['location'] == '/tasks'
    me = client.get('/api/v1/auth/me')
    assert me.status_code == 200
    assert me.json()['user']['roles'] == ['crm-user']


def test_register_too_many_pending_logins_are_limited(client, monkeypatch):
    monkeypatch.setattr('app.auth.MAX_PENDING_LOGINS', 2)
    start_registration(client)
    start_registration(client)
    response = client.get('/api/v1/auth/register', follow_redirects=False)
    assert response.status_code == 429
    assert response.json()['code'] == 'RATE_LIMITED'
