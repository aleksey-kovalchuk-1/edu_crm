"""Keycloak Admin API client: least-privilege access for listing users, reading/writing the
crm-superadmin realm role, and reading the realm's password policy.

Requires the `edu-crm-admin` service-account client (deploy/keycloak/realm-edu-crm.json) to have
been granted view-users/manage-users/view-realm on the realm-management client — done live via
scripts/keycloak-add-admin-permissions.sh (see docs/decisions.md), not via realm-import JSON.

`KeycloakAdminClient.is_configured()` is False whenever KEYCLOAK_ADMIN_CLIENT_ID/_SECRET are unset
(the default) — callers must check this and degrade to "admin features unavailable" rather than
calling any other method, which will raise.
"""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10.0
TOKEN_REFRESH_MARGIN_SECONDS = 10


class KeycloakAdminError(Exception):
    """Keycloak rejected the request (bad credentials, not found, etc). The message is for server logs only."""


class KeycloakAdminUnavailable(KeycloakAdminError):
    """Keycloak could not be reached or answered with a server error."""


class AdminUser:
    def __init__(self, id, email, username, roles):
        self.id = id
        self.email = email
        self.username = username
        self.roles = roles


class KeycloakAdminClient:
    """Talks to Keycloak's Admin REST API using a service-account (client_credentials) token from
    the `edu-crm-admin` client. Every method except `is_configured()` raises `KeycloakAdminError`
    (or its subclass `KeycloakAdminUnavailable` for connectivity/5xx failures) if the admin client
    is not configured or Keycloak rejects the request.
    """

    def __init__(self, *, base_url, client_id, client_secret, http_client):
        self._base_url = base_url.rstrip('/') if base_url else ''
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client
        self._token = None
        self._token_expires_at = 0.0
        self._role_id_cache = {}

    def is_configured(self):
        return bool(self._base_url and self._client_id and self._client_secret)

    def find_user_by_email(self, email):
        response = self._request('GET', '/users', params={'email': email, 'exact': 'true'})
        rows = response.json()
        if not rows:
            return None
        return self._to_admin_user(rows[0])

    def list_users(self, *, query=''):
        params = {'search': query} if query else {}
        response = self._request('GET', '/users', params=params)
        return [self._to_admin_user(row) for row in response.json()]

    def assign_realm_role(self, user_id, role_name):
        self._request(
            'POST', f'/users/{user_id}/role-mappings/realm',
            json=[{'id': self._role_id(role_name), 'name': role_name}],
        )

    def remove_realm_role(self, user_id, role_name):
        self._request(
            'DELETE', f'/users/{user_id}/role-mappings/realm',
            json=[{'id': self._role_id(role_name), 'name': role_name}],
        )

    def count_users_with_role(self, role_name):
        return sum(1 for user in self.list_users() if role_name in user.roles)

    def get_password_policy(self):
        response = self._request('GET', '')
        return response.json().get('passwordPolicy', '')

    def _to_admin_user(self, row):
        return AdminUser(
            id=row['id'], email=row.get('email', ''), username=row.get('username', ''),
            roles=self._realm_roles_of(row['id']),
        )

    def _realm_roles_of(self, user_id):
        response = self._request('GET', f'/users/{user_id}/role-mappings/realm')
        return [row['name'] for row in response.json()]

    def _role_id(self, role_name):
        """Keycloak's role-mappings endpoints identify roles by id, not name, so assigning or
        removing a role first resolves its id via GET .../roles/{role-name}. Cached per client
        instance since realm roles don't change id at runtime.
        """
        if role_name not in self._role_id_cache:
            response = self._request('GET', f'/roles/{role_name}')
            self._role_id_cache[role_name] = response.json()['id']
        return self._role_id_cache[role_name]

    def _admin_token(self):
        now = time.monotonic()
        if self._token and now < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token
        try:
            response = self._http.post(
                f'{self._base_url}/realms/edu-crm/protocol/openid-connect/token',
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self._client_id,
                    'client_secret': self._client_secret,
                },
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise KeycloakAdminUnavailable(f'admin token request failed: {error}') from error
        if response.status_code == 401:
            raise KeycloakAdminError('admin client credentials rejected')
        if response.status_code >= 500:
            raise KeycloakAdminUnavailable(f'admin token endpoint returned {response.status_code}')
        if response.status_code != 200:
            raise KeycloakAdminError(f'admin token endpoint returned {response.status_code}')
        body = response.json()
        self._token = body['access_token']
        self._token_expires_at = now + body.get('expires_in', 60)
        return self._token

    def _request(self, method, path, **kwargs):
        token = self._admin_token()
        try:
            response = self._http.request(
                method, f'{self._base_url}/admin/realms/edu-crm{path}',
                headers={'Authorization': f'Bearer {token}'}, timeout=HTTP_TIMEOUT_SECONDS, **kwargs,
            )
        except httpx.HTTPError as error:
            raise KeycloakAdminUnavailable(f'{path} unreachable: {error}') from error
        if response.status_code >= 500:
            raise KeycloakAdminUnavailable(f'{path} returned {response.status_code}')
        if response.status_code >= 400:
            raise KeycloakAdminError(f'{path} returned {response.status_code}')
        return response
