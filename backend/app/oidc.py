"""Minimal OpenID Connect client for Keycloak: authorization code with PKCE, refresh, back-channel logout,
ID token verification.

Browser-facing URLs use the public issuer (the value in the token's `iss` claim); server-to-server calls
(token, logout and signing-key endpoints) use the internal base URL on the Compose network.
"""
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from .security import tokens_match

logger = logging.getLogger(__name__)

CRM_ROLES = frozenset({'crm-user', 'crm-supervisor', 'crm-admin'})
SIGNING_ALGORITHMS = ['RS256']
CLOCK_SKEW_SECONDS = 30
# ID tokens arrive straight from the token endpoint, so anything older points to a replay or a clock problem.
MAX_ID_TOKEN_AGE_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10


class OIDCError(Exception):
    """Keycloak rejected the request or the token is invalid. The message is for server logs only."""


class OIDCUnavailable(OIDCError):
    """Keycloak could not be reached or answered with a server error; nothing was decided about the user."""


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    id_token: str | None
    refresh_token: str | None


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    full_name: str
    roles: tuple[str, ...]


class OIDCClient:
    def __init__(self, *, issuer, internal_base_url, client_id, client_secret, http,
                 jwks_ttl_seconds=300, clock=time.monotonic, wall_clock=time.time):
        self.issuer = issuer.rstrip('/')
        self.client_id = client_id
        self._internal_base_url = internal_base_url.rstrip('/')
        self._client_secret = client_secret
        self._http = http
        self._jwks_ttl_seconds = jwks_ttl_seconds
        self._clock = clock
        self._wall_clock = wall_clock
        self._jwks = None
        self._jwks_loaded_at = 0.0

    def authorization_url(self, *, redirect_uri, state, nonce, code_challenge):
        query = urlencode({
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'scope': 'openid profile email',
            'state': state,
            'nonce': nonce,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        })
        return f'{self.issuer}/protocol/openid-connect/auth?{query}'

    def end_session_url(self, *, post_logout_redirect_uri):
        query = urlencode({'client_id': self.client_id, 'post_logout_redirect_uri': post_logout_redirect_uri})
        return f'{self.issuer}/protocol/openid-connect/logout?{query}'

    def exchange_code(self, *, code, redirect_uri, code_verifier):
        return self._token_request({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'code_verifier': code_verifier,
        })

    def refresh(self, refresh_token):
        return self._token_request({'grant_type': 'refresh_token', 'refresh_token': refresh_token})

    def end_session(self, refresh_token):
        """Ends the Keycloak SSO session from the server, so a closed browser tab cannot leave it signed in."""
        response = self._post('/protocol/openid-connect/logout', {'refresh_token': refresh_token})
        if response.status_code not in (200, 204):
            raise OIDCError(f'logout endpoint returned {response.status_code}: {response.text[:200]}')

    def verify_id_token(self, id_token, *, nonce=None):
        if not id_token:
            raise OIDCError('token response has no id_token')
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as error:
            raise OIDCError(f'malformed id_token: {error}') from error
        if header.get('alg') not in SIGNING_ALGORITHMS:
            raise OIDCError(f'unexpected id_token algorithm {header.get("alg")!r}')
        key = self._signing_key(header.get('kid'))
        try:
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=SIGNING_ALGORITHMS,
                audience=self.client_id,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
            )
        except jwt.PyJWTError as error:
            raise OIDCError(f'id_token rejected: {error}') from error
        if claims.get('azp') not in (None, self.client_id):
            raise OIDCError('id_token was issued to another client')
        if claims['iat'] < self._wall_clock() - MAX_ID_TOKEN_AGE_SECONDS:
            raise OIDCError('id_token is too old')
        if nonce is not None and not tokens_match(nonce, claims.get('nonce')):
            raise OIDCError('id_token nonce mismatch')

        raw_roles = claims.get('roles')
        roles = raw_roles if isinstance(raw_roles, list) else []
        email = claims.get('email') or ''
        return Identity(
            subject=claims['sub'],
            email=email,
            full_name=claims.get('name') or claims.get('preferred_username') or email or claims['sub'],
            # Keycloak also puts built-in roles (default-roles-*, offline_access) in the claim; only CRM roles matter.
            roles=tuple(sorted({role for role in roles if role in CRM_ROLES})),
        )

    def _post(self, path, data):
        try:
            response = self._http.post(
                f'{self._internal_base_url}{path}',
                data={**data, 'client_id': self.client_id, 'client_secret': self._client_secret},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise OIDCUnavailable(f'{path} unreachable: {error}') from error
        if response.status_code >= 500:
            raise OIDCUnavailable(f'{path} returned {response.status_code}')
        return response

    def _token_request(self, data):
        response = self._post('/protocol/openid-connect/token', data)
        if response.status_code != 200:
            raise OIDCError(f'token endpoint returned {response.status_code}: {response.text[:200]}')
        try:
            body = response.json()
        except ValueError as error:
            raise OIDCUnavailable('token endpoint returned invalid JSON') from error
        if not isinstance(body, dict) or not body.get('access_token'):
            raise OIDCUnavailable('token response has no access_token')
        return TokenSet(access_token=body['access_token'], id_token=body.get('id_token'), refresh_token=body.get('refresh_token'))

    def _signing_key(self, kid):
        stale = self._jwks is None or self._clock() - self._jwks_loaded_at > self._jwks_ttl_seconds
        if stale:
            self._load_jwks()
        key = self._find_key(kid)
        if key is None and not stale:
            # Keycloak rotates keys; refetch once so a freshly rotated key is accepted.
            self._load_jwks()
            key = self._find_key(kid)
        if key is None:
            raise OIDCError(f'no signing key for kid {kid!r}')
        return key

    def _load_jwks(self):
        try:
            response = self._http.get(f'{self._internal_base_url}/protocol/openid-connect/certs', timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            self._jwks = jwt.PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as error:
            raise OIDCUnavailable(f'cannot load signing keys: {error}') from error
        self._jwks_loaded_at = self._clock()

    def _find_key(self, kid):
        for jwk in self._jwks.keys:
            if jwk.key_id == kid:
                return jwk.key
        return None
