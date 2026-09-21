"""A stand-in for Keycloak in tests: signs ID tokens with a local RSA key and answers token, logout and JWKS requests."""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = 'http://localhost:8080/auth/realms/edu-crm'
INTERNAL_BASE_URL = 'http://keycloak.test/auth/realms/edu-crm'
CLIENT_ID = 'edu-crm-api'
CLIENT_SECRET = 'test-client-secret'

ADMIN_BASE_URL = 'http://keycloak.test/auth'
ADMIN_CLIENT_ID = 'edu-crm-admin'
ADMIN_CLIENT_SECRET = 'test-admin-secret'
ADMIN_PATH_PREFIX = '/auth/admin/realms/edu-crm'


def s256(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')


class FakeKeycloak:
    def __init__(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = 'test-key-1'
        self.codes = {}
        self.refresh_tokens = {}
        self.token_requests = []
        self.logouts = []
        self.jwks_requests = 0
        self.fail_refresh = False
        self.omit_id_token_on_refresh = False
        # Simulates an outage: every endpoint answers 503.
        self.unavailable = False
        self.admin_users = {}  # id -> {"id", "email", "username", "roles": [...]}
        self.realm_password_policy = "length(12) and notUsername and notEmail and passwordHistory(3)"

    def jwks(self):
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        public.update(kid=self.kid, use='sig', alg='RS256')
        return {'keys': [public]}

    def rotate_key(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = f'test-key-{secrets.token_hex(4)}'

    def id_token(self, claims, *, key=None, kid=None, algorithm='RS256'):
        now = int(time.time())
        payload = {'iss': ISSUER, 'aud': CLIENT_ID, 'azp': CLIENT_ID, 'iat': now, 'exp': now + 300, **claims}
        return jwt.encode(payload, key or self.private_key, algorithm=algorithm, headers={'kid': kid or self.kid})

    def issue_code(self, *, nonce, code_challenge, subject='kc-user-1', email='anna.demo@demo.local', name='Анна Демо', roles=('crm-user',)):
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            'claims': {'sub': subject, 'email': email, 'name': name, 'roles': list(roles)},
            'nonce': nonce,
            'code_challenge': code_challenge,
        }
        return code

    def set_roles(self, subject, roles):
        for claims in self.refresh_tokens.values():
            if claims['sub'] == subject:
                claims['roles'] = list(roles)

    def add_admin_user(self, *, id, email, username, roles):
        self.admin_users[id] = {'id': id, 'email': email, 'username': username, 'roles': list(roles)}

    def handler(self, request):
        if self.unavailable:
            return httpx.Response(503, text='Service Unavailable')
        path = request.url.path
        if path.endswith('/protocol/openid-connect/certs'):
            self.jwks_requests += 1
            return httpx.Response(200, json=self.jwks())

        # Admin API surface: token (client_credentials, admin client) + /admin/realms/edu-crm/*.
        if path.endswith('/protocol/openid-connect/token') and b'grant_type=client_credentials' in request.content:
            form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            if form.get('client_id') != ADMIN_CLIENT_ID or form.get('client_secret') != ADMIN_CLIENT_SECRET:
                return httpx.Response(401, json={'error': 'unauthorized_client'})
            return httpx.Response(200, json={'access_token': 'admin-access-token', 'expires_in': 60})
        if path == ADMIN_PATH_PREFIX or path.startswith(ADMIN_PATH_PREFIX + '/'):
            return self._admin_handler(request, path)

        # (everything below this point is the existing OIDC login/refresh/logout handling, unchanged)
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if form.get('client_id') != CLIENT_ID or form.get('client_secret') != CLIENT_SECRET:
            return httpx.Response(401, json={'error': 'unauthorized_client'})

        if path.endswith('/protocol/openid-connect/logout'):
            if self.refresh_tokens.pop(form.get('refresh_token'), None) is None:
                return httpx.Response(400, json={'error': 'invalid_grant'})
            self.logouts.append(form['refresh_token'])
            return httpx.Response(204)

        if not path.endswith('/protocol/openid-connect/token'):
            return httpx.Response(404)
        self.token_requests.append(form)

        if form.get('grant_type') == 'authorization_code':
            entry = self.codes.pop(form.get('code'), None)
            if entry is None or s256(form.get('code_verifier', '')) != entry['code_challenge']:
                return httpx.Response(400, json={'error': 'invalid_grant'})
            return self._tokens(entry['claims'], nonce=entry['nonce'])

        if form.get('grant_type') == 'refresh_token':
            # Refresh tokens are single use, as in the realm (revokeRefreshToken, refreshTokenMaxReuse 0).
            claims = self.refresh_tokens.pop(form.get('refresh_token'), None)
            if claims is None or self.fail_refresh:
                return httpx.Response(400, json={'error': 'invalid_grant'})
            return self._tokens(claims, include_id_token=not self.omit_id_token_on_refresh)

        return httpx.Response(400, json={'error': 'unsupported_grant_type'})

    def _tokens(self, claims, nonce=None, include_id_token=True):
        refresh = secrets.token_urlsafe(16)
        self.refresh_tokens[refresh] = claims
        body = {'access_token': 'access-token', 'refresh_token': refresh}
        if include_id_token:
            body['id_token'] = self.id_token({**claims, 'nonce': nonce} if nonce else dict(claims))
        return httpx.Response(200, json=body)

    def _admin_handler(self, request, path):
        suffix = path[len(ADMIN_PATH_PREFIX):].lstrip('/')
        if suffix == 'users' and request.method == 'GET':
            email = request.url.params.get('email')
            users = list(self.admin_users.values())
            if email:
                users = [u for u in users if u['email'] == email]
            return httpx.Response(200, json=[
                {'id': u['id'], 'email': u['email'], 'username': u['username']} for u in users
            ])
        if suffix.startswith('users/') and suffix.endswith('/role-mappings/realm') and request.method in ('POST', 'DELETE'):
            user_id = suffix[len('users/'):-len('/role-mappings/realm')]
            roles = json.loads(request.content)
            user = self.admin_users.get(user_id)
            if user is None:
                return httpx.Response(404)
            names = {r['name'] for r in roles}
            if request.method == 'POST':
                user['roles'] = user['roles'] + [name for name in names if name not in user['roles']]
            else:
                user['roles'] = [r for r in user['roles'] if r not in names]
            return httpx.Response(204)
        if suffix.startswith('users/') and suffix.endswith('/role-mappings/realm') and request.method == 'GET':
            user_id = suffix[len('users/'):-len('/role-mappings/realm')]
            user = self.admin_users.get(user_id)
            if user is None:
                return httpx.Response(404)
            return httpx.Response(200, json=[{'id': r, 'name': r} for r in user['roles']])
        if suffix.startswith('roles/') and request.method == 'GET':
            role_name = suffix[len('roles/'):]
            return httpx.Response(200, json={'id': role_name, 'name': role_name})
        if suffix == '' and request.method == 'GET':
            return httpx.Response(200, json={'passwordPolicy': self.realm_password_policy})
        return httpx.Response(404)

    def http_client(self):
        return httpx.Client(transport=httpx.MockTransport(self.handler))
