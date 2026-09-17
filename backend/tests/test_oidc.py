import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.oidc import MAX_ID_TOKEN_AGE_SECONDS, OIDCClient, OIDCError, OIDCUnavailable
from fake_keycloak import CLIENT_ID, CLIENT_SECRET, INTERNAL_BASE_URL, ISSUER, FakeKeycloak, s256


@pytest.fixture
def keycloak():
    return FakeKeycloak()


def make_client(keycloak, **overrides):
    options = dict(issuer=ISSUER, internal_base_url=INTERNAL_BASE_URL, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http=keycloak.http_client())
    options.update(overrides)
    return OIDCClient(**options)


def test_authorization_url_uses_public_issuer_and_pkce(keycloak):
    url = make_client(keycloak).authorization_url(redirect_uri='http://localhost:8080/api/v1/auth/callback', state='s', nonce='n', code_challenge='c')
    parts = urlsplit(url)
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == f'{ISSUER}/protocol/openid-connect/auth'
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert query == {
        'response_type': 'code', 'client_id': CLIENT_ID, 'redirect_uri': 'http://localhost:8080/api/v1/auth/callback',
        'scope': 'openid profile email', 'state': 's', 'nonce': 'n', 'code_challenge': 'c', 'code_challenge_method': 'S256',
    }


def test_authorization_url_registration_uses_the_registrations_endpoint(keycloak):
    url = make_client(keycloak).authorization_url(
        redirect_uri='http://localhost:8080/api/v1/auth/callback', state='s', nonce='n', code_challenge='c', registration=True,
    )
    parts = urlsplit(url)
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == f'{ISSUER}/protocol/openid-connect/registrations'
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert query['response_type'] == 'code' and query['client_id'] == CLIENT_ID and query['code_challenge_method'] == 'S256'


def test_valid_token_yields_identity_with_crm_roles_only(keycloak):
    token = keycloak.id_token({'sub': 'kc-1', 'email': 'a@demo.local', 'name': 'Анна Демо', 'nonce': 'n',
                               'roles': ['default-roles-edu-crm', 'offline_access', 'crm-supervisor', 'crm-user']})
    identity = make_client(keycloak).verify_id_token(token, nonce='n')
    assert identity.subject == 'kc-1'
    assert identity.full_name == 'Анна Демо'
    assert identity.roles == ('crm-supervisor', 'crm-user')


@pytest.mark.parametrize('claims, reason', [
    ({'iss': 'http://attacker.example/realms/edu-crm'}, 'issuer'),
    ({'aud': 'another-client'}, 'audience'),
    ({'exp': int(time.time()) - 3600}, 'expired'),
    ({'nonce': 'other'}, 'nonce'),
])
def test_rejects_invalid_claims(keycloak, claims, reason):
    token = keycloak.id_token({'sub': 'kc-1', 'nonce': 'n', 'roles': ['crm-user'], **claims})
    with pytest.raises(OIDCError):
        make_client(keycloak).verify_id_token(token, nonce='n')


def test_rejects_token_signed_by_unknown_key(keycloak):
    foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = keycloak.id_token({'sub': 'kc-1'}, key=foreign_key)
    with pytest.raises(OIDCError):
        make_client(keycloak).verify_id_token(token)


def test_rejects_unsigned_token(keycloak):
    import jwt
    token = jwt.encode({'sub': 'kc-1', 'iss': ISSUER, 'aud': CLIENT_ID, 'iat': int(time.time()), 'exp': int(time.time()) + 60}, key=None, algorithm='none')
    with pytest.raises(OIDCError):
        make_client(keycloak).verify_id_token(token)


def test_rotated_key_is_fetched_once(keycloak):
    client = make_client(keycloak)
    client.verify_id_token(keycloak.id_token({'sub': 'kc-1'}))
    keycloak.rotate_key()
    client.verify_id_token(keycloak.id_token({'sub': 'kc-1'}))
    assert keycloak.jwks_requests == 2


def test_code_exchange_requires_matching_verifier(keycloak):
    client = make_client(keycloak)
    code = keycloak.issue_code(nonce='n', code_challenge='does-not-match')
    with pytest.raises(OIDCError):
        client.exchange_code(code=code, redirect_uri='http://localhost:8080/api/v1/auth/callback', code_verifier='verifier')


def test_refresh_failure_raises(keycloak):
    with pytest.raises(OIDCError):
        make_client(keycloak).refresh('unknown-refresh-token')


def test_unreachable_provider_is_reported_as_unavailable():
    def unreachable(request):
        raise httpx.ConnectError('connection refused', request=request)

    client = OIDCClient(issuer=ISSUER, internal_base_url=INTERNAL_BASE_URL, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                        http=httpx.Client(transport=httpx.MockTransport(unreachable)))
    with pytest.raises(OIDCUnavailable):
        client.refresh('token')


def test_provider_server_error_is_unavailable_not_a_rejection(keycloak):
    keycloak.unavailable = True
    with pytest.raises(OIDCUnavailable):
        make_client(keycloak).refresh('token')


def test_rejected_refresh_is_not_reported_as_unavailable(keycloak):
    with pytest.raises(OIDCError) as raised:
        make_client(keycloak).refresh('unknown-refresh-token')
    assert not isinstance(raised.value, OIDCUnavailable)


def test_signing_keys_outage_is_unavailable(keycloak):
    token = keycloak.id_token({'sub': 'kc-1'})
    keycloak.unavailable = True
    with pytest.raises(OIDCUnavailable):
        make_client(keycloak).verify_id_token(token)


def test_token_issued_to_another_client_is_rejected(keycloak):
    token = keycloak.id_token({'sub': 'kc-1', 'azp': 'another-client'})
    with pytest.raises(OIDCError):
        make_client(keycloak).verify_id_token(token)


def test_old_token_is_rejected_even_if_not_expired(keycloak):
    issued = int(time.time()) - MAX_ID_TOKEN_AGE_SECONDS - 120
    token = keycloak.id_token({'sub': 'kc-1', 'iat': issued, 'exp': int(time.time()) + 3600})
    with pytest.raises(OIDCError):
        make_client(keycloak).verify_id_token(token)


def test_end_session_revokes_refresh_token_at_keycloak(keycloak):
    client = make_client(keycloak)
    code = keycloak.issue_code(nonce='n', code_challenge=s256('verifier-' + 'x' * 40))
    tokens = client.exchange_code(code=code, redirect_uri='http://localhost:8080/api/v1/auth/callback', code_verifier='verifier-' + 'x' * 40)
    client.end_session(tokens.refresh_token)
    assert keycloak.logouts == [tokens.refresh_token]
    with pytest.raises(OIDCError):
        client.refresh(tokens.refresh_token)
