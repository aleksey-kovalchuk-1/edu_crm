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
        # Simulates a cold-start race: the next N requests (any endpoint) answer 503, then normal
        # responses resume. Decremented on every request while > 0.
        self.unavailable_calls_remaining = 0
        self.admin_users = {}  # id -> {"id", "email", "username", "roles": [...]}
        self.logged_out_users = []
        self.fail_role_assignment = False
        self.fail_role_removal = False
        self.realm_password_policy = "length(12) and notUsername and notEmail and passwordHistory(3)"
        self.realm_events_enabled = False
        self.admin_sessions = set()   # Keycloak session ids that are still active
        self.admin_events = []        # stored login events ({'time', 'type', 'userId', ...})
        self.events_forbidden = False  # service account lacks view-events
        self.fail_session_delete = False
        self.registration_email_as_username = False
        self.edit_username_allowed = True
        # Malformed-response simulation for the admin API, settable per test:
        #   'not_json'    -> GET /users returns 200 with a non-JSON body.
        #   'wrong_shape' -> GET /users returns 200 with a JSON object instead of a JSON array.
        self.malformed_users_response = None
        # When True, the admin client_credentials token endpoint returns 200 with a JSON body that
        # has no access_token key.
        self.token_response_missing_access_token = False

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

    def issue_code(self, *, nonce, code_challenge, subject='kc-user-1', email='anna.demo@demo.local', name='Анна Демо',
                   roles=('crm-user',), given_name=None, family_name=None, sid=None):
        code = secrets.token_urlsafe(16)
        claims = {'sub': subject, 'email': email, 'name': name, 'roles': list(roles)}
        if sid is not None:
            claims['sid'] = sid
        if given_name is not None:
            claims['given_name'] = given_name
        if family_name is not None:
            claims['family_name'] = family_name
        self.codes[code] = {'claims': claims, 'nonce': nonce, 'code_challenge': code_challenge}
        return code

    def set_roles(self, subject, roles):
        for claims in self.refresh_tokens.values():
            if claims['sub'] == subject:
                claims['roles'] = list(roles)

    def add_admin_user(self, *, id, email, username, roles, first_name='', last_name='', enabled=True):
        self.admin_users[id] = {
            'id': id, 'email': email, 'username': username, 'roles': list(roles),
            'firstName': first_name, 'lastName': last_name, 'enabled': enabled,
        }

    def handler(self, request):
        if self.unavailable:
            return httpx.Response(503, text='Service Unavailable')
        if self.unavailable_calls_remaining > 0:
            self.unavailable_calls_remaining -= 1
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
            if self.token_response_missing_access_token:
                return httpx.Response(200, json={'expires_in': 60})
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
            if self.malformed_users_response == 'not_json':
                return httpx.Response(200, text='not json')
            if self.malformed_users_response == 'wrong_shape':
                return httpx.Response(200, json={'not': 'a list'})
            email = request.url.params.get('email')
            users = list(self.admin_users.values())
            if email:
                users = [u for u in users if u['email'] == email]
            else:
                first = int(request.url.params.get('first', '0'))
                maximum = int(request.url.params.get('max', '100'))
                users = users[first:first + maximum]
            return httpx.Response(200, json=[
                {field: u[field] for field in ('id', 'email', 'username', 'firstName', 'lastName', 'enabled')}
                for u in users
            ])
        if suffix == 'users' and request.method == 'POST':
            body = json.loads(request.content)
            if any(u['username'].casefold() == body['username'].casefold() or
                   u['email'].casefold() == body['email'].casefold() for u in self.admin_users.values()):
                return httpx.Response(409)
            user_id = f'kc-created-{len(self.admin_users) + 1}'
            self.add_admin_user(
                id=user_id, email=body['email'],
                username=body['email'] if self.registration_email_as_username else body['username'], roles=[],
                first_name=body.get('firstName', ''), last_name=body.get('lastName', ''),
                enabled=body.get('enabled', True),
            )
            self.admin_users[user_id]['temporary_password'] = body['credentials'][0]['value']
            return httpx.Response(201, headers={'Location': f'{ADMIN_BASE_URL}/admin/realms/edu-crm/users/{user_id}'})
        if suffix.startswith('users/') and request.method == 'GET' and '/' not in suffix[len('users/'):]:
            user = self.admin_users.get(suffix[len('users/'):])
            if user is None:
                return httpx.Response(404)
            return httpx.Response(200, json={k: v for k, v in user.items() if k not in ('roles', 'temporary_password')})
        if suffix.startswith('users/') and request.method in ('PUT', 'DELETE') and '/' not in suffix[len('users/'):]:
            user_id = suffix[len('users/'):]
            if user_id not in self.admin_users:
                return httpx.Response(404)
            if request.method == 'DELETE':
                del self.admin_users[user_id]
            else:
                body = json.loads(request.content)
                if not self.edit_username_allowed and body.get('username', self.admin_users[user_id]['username']) != self.admin_users[user_id]['username']:
                    return httpx.Response(400, json={'field': 'username', 'errorMessage': 'error-user-attribute-read-only'})
                if self.registration_email_as_username:
                    body['username'] = body.get('email', self.admin_users[user_id]['email'])
                self.admin_users[user_id].update(body)
                if 'firstName' in body or 'lastName' in body:
                    # Real Keycloak puts the new names into the next refreshed token.
                    stored = self.admin_users[user_id]
                    for claims in self.refresh_tokens.values():
                        if claims['sub'] == user_id:
                            claims.update(
                                given_name=stored.get('firstName', ''), family_name=stored.get('lastName', ''),
                                name=f"{stored.get('firstName', '')} {stored.get('lastName', '')}".strip(),
                            )
            return httpx.Response(204)
        if suffix.startswith('users/') and request.method == 'GET' and '/' not in suffix[len('users/'):]:
            user = self.admin_users.get(suffix[len('users/'):])
            return httpx.Response(200, json=user) if user else httpx.Response(404)
        if suffix.startswith('users/') and suffix.endswith('/logout') and request.method == 'POST':
            user_id = suffix[len('users/'):-len('/logout')]
            if user_id not in self.admin_users:
                return httpx.Response(404)
            self.logged_out_users.append(user_id)
            return httpx.Response(204)
        if suffix.startswith('users/') and suffix.endswith('/reset-password') and request.method == 'PUT':
            user_id = suffix[len('users/'):-len('/reset-password')]
            if user_id not in self.admin_users:
                return httpx.Response(404)
            self.admin_users[user_id]['temporary_password'] = json.loads(request.content)['value']
            return httpx.Response(204)
        if suffix.startswith('roles/') and suffix.endswith('/users') and request.method == 'GET':
            role_name = suffix[len('roles/'):-len('/users')]
            members = [u for u in self.admin_users.values() if role_name in u['roles']]
            return httpx.Response(200, json=[
                {'id': u['id'], 'email': u['email'], 'username': u['username']} for u in members
            ])
        if suffix.startswith('users/') and suffix.endswith('/role-mappings/realm') and request.method in ('POST', 'DELETE'):
            if self.fail_role_assignment and request.method == 'POST':
                return httpx.Response(503)
            if self.fail_role_removal and request.method == 'DELETE':
                return httpx.Response(503)
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
            return httpx.Response(200, json={
                'passwordPolicy': self.realm_password_policy, 'bruteForceProtected': True,
                'failureFactor': 30, 'eventsEnabled': self.realm_events_enabled,
                'registrationEmailAsUsername': self.registration_email_as_username,
                'editUsernameAllowed': self.edit_username_allowed,
            })
        if suffix.startswith('sessions/') and request.method == 'DELETE':
            if self.fail_session_delete:
                return httpx.Response(503)
            sid = suffix[len('sessions/'):]
            if sid not in self.admin_sessions:
                return httpx.Response(404)
            self.admin_sessions.discard(sid)
            return httpx.Response(204)
        if suffix == 'events' and request.method == 'GET':
            if self.events_forbidden:
                return httpx.Response(403)
            user = request.url.params.get('user')
            types = set(request.url.params.get_list('type'))
            rows = [e for e in self.admin_events if e.get('userId') == user and (not types or e['type'] in types)]
            return httpx.Response(200, json=rows[: int(request.url.params.get('max', '100'))])
        return httpx.Response(404)

    def http_client(self):
        return httpx.Client(transport=httpx.MockTransport(self.handler))
