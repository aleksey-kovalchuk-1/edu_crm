"""Keycloak Admin API client: least-privilege access for listing users, reading/writing the
crm-superadmin realm role, and reading the realm's password policy.

Requires the `edu-crm-admin` service-account client (deploy/keycloak/realm-edu-crm.json) to have
been granted view-users/manage-users/view-realm on the realm-management client — done live via
scripts/keycloak-grant-admin-permissions.sh (see docs/decisions.md), not via realm-import JSON.

`KeycloakAdminClient.is_configured()` is False whenever KEYCLOAK_ADMIN_CLIENT_ID/_SECRET are unset
(the default) — callers must check this and degrade to "admin features unavailable" rather than
calling any other method, which will raise.
"""
import time

import httpx

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
        rows = self._json_list(response)
        if not rows:
            return None
        return self._to_admin_user(rows[0])

    def list_users(self, *, query='', max_results=200, first=0):
        """General-purpose user listing. Keycloak defaults `max` to 100 when unset, so callers that
        might see more users than `max_results` must page explicitly via `first` — this method does
        not do that for them.
        """
        params = {'max': max_results, 'first': first}
        if query:
            params['search'] = query
        response = self._request('GET', '/users', params=params)
        return [self._to_admin_user(row) for row in self._json_list(response)]

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
        """Counts realm-role members directly via .../roles/{role-name}/users, rather than listing
        every user and filtering client-side — avoids under-counting on realms with more users than
        list_users()'s page size, and needs only view-users (already granted).
        """
        response = self._request('GET', f'/roles/{role_name}/users', params={'max': 1000})
        return len(self._json_list(response))

    def get_password_policy(self):
        response = self._request('GET', '')
        body = self._json(response)
        if not isinstance(body, dict):
            raise KeycloakAdminError(f'expected a JSON object for realm info, got {type(body).__name__}')
        return body.get('passwordPolicy', '')

    def _to_admin_user(self, row):
        try:
            user_id = row['id']
        except (TypeError, KeyError) as error:
            raise KeycloakAdminError(f'unexpected user response shape: {error}') from error
        return AdminUser(
            id=user_id, email=row.get('email', ''), username=row.get('username', ''),
            roles=self._realm_roles_of(user_id),
        )

    def _realm_roles_of(self, user_id):
        response = self._request('GET', f'/users/{user_id}/role-mappings/realm')
        rows = self._json_list(response)
        try:
            return [row['name'] for row in rows]
        except (TypeError, KeyError) as error:
            raise KeycloakAdminError(f'unexpected role-mapping response shape: {error}') from error

    def _role_id(self, role_name):
        """Keycloak's role-mappings endpoints identify roles by id, not name, so assigning or
        removing a role first resolves its id via GET .../roles/{role-name}. Cached per client
        instance since realm roles don't change id at runtime.
        """
        if role_name not in self._role_id_cache:
            response = self._request('GET', f'/roles/{role_name}')
            body = self._json(response)
            if not isinstance(body, dict) or 'id' not in body:
                raise KeycloakAdminError(f'unexpected response shape for role {role_name!r}')
            self._role_id_cache[role_name] = body['id']
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
        body = self._json(response)
        if not isinstance(body, dict):
            raise KeycloakAdminError(f'token response was not a JSON object (got {type(body).__name__})')
        access_token = body.get('access_token')
        if not access_token:
            raise KeycloakAdminError('token response has no access_token')
        self._token = access_token
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
        if response.status_code == 401:
            # A cached token Keycloak no longer accepts — drop it so the next call re-authenticates
            # instead of replaying the same rejected token until it naturally expires.
            self._token = None
            raise KeycloakAdminError(f'{path} returned 401')
        if response.status_code >= 400:
            raise KeycloakAdminError(f'{path} returned {response.status_code}')
        return response

    def _json(self, response):
        """response.json() guarded against a 2xx response with a non-JSON body (httpx raises a
        ValueError subclass, not KeycloakAdminError, in that case)."""
        try:
            return response.json()
        except ValueError as error:
            raise KeycloakAdminError(f'invalid JSON response: {error}') from error

    def _json_list(self, response):
        body = self._json(response)
        if not isinstance(body, list):
            raise KeycloakAdminError(f'expected a JSON array, got {type(body).__name__}')
        return body
