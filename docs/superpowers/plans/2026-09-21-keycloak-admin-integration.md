# Keycloak Admin Integration + Superadmin Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the backend real, least-privilege access to Keycloak's Admin API (for listing users, reading roles, assigning/removing the new `crm-superadmin` role, and reading the live password policy), introduce a `crm-superadmin` CRM role that is never silently dropped from tokens, and deterministically bootstrap exactly one initial superadmin with a mechanism that can never leave the system with zero.

**Architecture:** A new Keycloak client (`edu-crm-admin`, service-account only, no browser flow) authenticates via `client_credentials` and is granted only the realm-management roles it actually needs (`view-users`, `manage-users`, `view-realm`) via a one-time `kcadm`-run script — mirroring how `scripts/keycloak-add-public-origin.sh` already modifies a live realm rather than relying on fragile hand-written realm-export JSON for service-account role grants. A new `backend/app/keycloak_admin.py` wraps this client (token fetch+cache, user lookup, role assignment, password policy read), reusing the same injectable-`http_client` pattern `OIDCClient` already uses so it can be faked in tests exactly like `tests/fake_keycloak.py` already fakes the login flow. Bootstrap runs as a new step in `backend/docker-entrypoint.sh` (same place migrations/demo-seeding already run — a shell step before the server starts, fully decoupled from `create_app()`/test construction, so it can never accidentally fire during the test suite), controlled by an optional `INITIAL_SUPERADMIN_EMAIL` env var, and fails open (logs a warning, exits 0) rather than blocking container startup if Keycloak isn't reachable yet or the email doesn't match any user — this is bootstrap convenience, not a hard dependency the whole app should die over.

**Tech Stack:** FastAPI + httpx (backend/app/keycloak_admin.py, mirroring backend/app/oidc.py's style), Keycloak 26 realm-management REST API, `kcadm.sh` (already used in this repo's `scripts/keycloak-add-public-origin.sh`).

**Spec:** No separate spec doc — scoped in conversation on 2026-09-21 (the full 7-section "Настройки" request, this project's slice 2 of 8), with an explicit architecture simplification from the owner: exactly one deterministic `superadmin` role gates all admin/system surfaces; no permission matrix; the existing `crm-user`/`crm-supervisor`/`crm-admin` roles are untouched for everything else; the Keycloak service account gets least-privilege realm-management permissions, never exposed to the frontend, credentials in env/secret config only, never committed.

## Global Constraints

- Credentials for the new Keycloak service account must never reach the frontend, must live only in `deploy/local/*.env` (gitignored, generated via `scripts/generate-dev-secrets.sh`'s existing pattern), and must never be committed.
- No large RBAC/permission editor. One role (`crm-superadmin`), one clear purpose: gates admin/system functions. The existing 3-role model is untouched.
- The Keycloak service account gets least-privilege permissions — only what listing users, assigning/removing the `crm-superadmin` realm role, and reading the realm's password policy actually require (`view-users`, `manage-users`, `view-realm`). Do not grant `manage-realm`, `manage-clients`, or anything broader "just in case."
- Changing the password policy itself is explicitly out of scope — this integration only reads it. "Only administrators may change it, through the real identity provider" means Keycloak's own admin console, not this API.
- The system must never end up with zero superadmins from an automated process. This plan's bootstrap step only ever adds a superadmin when none exists — it never removes one, and it must be idempotent (safe to run on every container start).
- Bootstrap must never block or crash API startup — a misconfigured or absent `INITIAL_SUPERADMIN_EMAIL`, or Keycloak being briefly unreachable when the container starts, must log clearly and let the API come up normally.
- Do not touch the frontend in this plan — slice 1 already added the (currently empty-of-real-users) `superadmin`-gated menu items; this plan is backend-only infrastructure. A later slice (6: Пользователи и роли) builds the UI that consumes this.
- Do not push or merge; local commits only.

---

### Task 1: Realm client, secrets, and role plumbing

**Files:**
- Modify: `deploy/keycloak/realm-edu-crm.json` (new `crm-superadmin` realm role, new `edu-crm-admin` service-account client)
- Modify: `scripts/generate-dev-secrets.sh` (generate and write the new client's secret)
- Modify: `backend/app/oidc.py` (`CRM_ROLES` — add `crm-superadmin`, or the role is silently stripped from every token)
- Modify: `backend/app/auth.py` (`ROLE_SUPERADMIN` constant)
- Modify: `backend/app/settings.py` (new optional `keycloak_admin_client_id`/`keycloak_admin_client_secret`/`keycloak_admin_base_url` fields — optional, not in `REQUIRED_AUTH_SETTINGS`, so existing deployments without them keep working with admin features simply unavailable, exactly like `sms_provider_url`/`sms_provider_api_key` already work)
- Modify: `compose.yaml` (`api` service: `KEYCLOAK_ADMIN_CLIENT_ID` in `environment:`, relies on `KEYCLOAK_ADMIN_CLIENT_SECRET` arriving via the existing `deploy/local/api.env` `env_file`)
- Test: `backend/tests/test_auth.py` or wherever `CRM_ROLES`/role-filtering is already tested (grep first)

**Interfaces:**
- Produces: `ROLE_SUPERADMIN = 'crm-superadmin'` (in `backend/app/auth.py`, alongside the existing `ROLE_USER`/`ROLE_SUPERVISOR`/`ROLE_ADMIN` — do NOT add it to `ALL_ROLES`, since that tuple means "any signed-in CRM role" for the generic `any_role` dependency, and `crm-superadmin` is an orthogonal admin-only capability, not a 4th tier of the same ladder); `Settings.keycloak_admin_client_id: str`, `Settings.keycloak_admin_client_secret: str` (both default `''`), `Settings.keycloak_admin_base_url: str` (derived, see Step 4). Task 2's `KeycloakAdminClient` reads these three fields to decide whether admin features are configured at all.

- [ ] **Step 1: Add the realm role and the new client to the realm JSON**

In `deploy/keycloak/realm-edu-crm.json`, add to the `"roles": {"realm": [...]}` array (after the existing 3):
```json
      {
        "name": "crm-superadmin",
        "description": "Полный административный доступ: пользователи, роли, безопасность, конфигурация системы"
      }
```
Add a second client to the `"clients": [...]` array, after the existing `edu-crm-api` entry:
```json
    {
      "clientId": "edu-crm-admin",
      "name": "Образование CRM — административный доступ",
      "description": "Служебная учётная запись для Keycloak Admin API (список пользователей, роли, политика паролей)",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": false,
      "bearerOnly": false,
      "clientAuthenticatorType": "client-secret",
      "secret": "${EDU_CRM_ADMIN_CLIENT_SECRET}",
      "standardFlowEnabled": false,
      "implicitFlowEnabled": false,
      "directAccessGrantsEnabled": false,
      "serviceAccountsEnabled": true,
      "frontchannelLogout": false,
      "consentRequired": false,
      "fullScopeAllowed": false,
      "redirectUris": [],
      "webOrigins": []
    }
```
`serviceAccountsEnabled: true` auto-creates a `service-account-edu-crm-admin` user at realm-import time; its actual realm-management role grants are done live in Task 3 (not here — hand-writing service-account role-mapping exports in realm JSON is fragile and this repo already has a proven live-`kcadm` pattern for exactly this kind of post-import change, from `scripts/keycloak-add-public-origin.sh`).

- [ ] **Step 2: Extend the dev-secrets script**

In `scripts/generate-dev-secrets.sh`, add a new random secret alongside the existing ones:
```bash
admin_client_secret="$(random_text 40)"
```
Add `EDU_CRM_ADMIN_CLIENT_SECRET=$admin_client_secret` to the `keycloak_env` heredoc (alongside `EDU_CRM_CLIENT_SECRET`), and `KEYCLOAK_ADMIN_CLIENT_SECRET=$admin_client_secret` to the `api_env` heredoc (alongside `OIDC_CLIENT_SECRET`) — same value, two files, exactly mirroring how `client_secret`/`EDU_CRM_CLIENT_SECRET`/`OIDC_CLIENT_SECRET` already work for the login client.

- [ ] **Step 3: Add the role constant and fix the token-role allowlist**

In `backend/app/auth.py`, after the existing `ALL_ROLES = (ROLE_USER, ROLE_SUPERVISOR, ROLE_ADMIN)`:
```python
ROLE_SUPERADMIN = 'crm-superadmin'
```
(Deliberately not added to `ALL_ROLES` — see this task's Interfaces note above.)

In `backend/app/oidc.py`, change:
```python
CRM_ROLES = frozenset({'crm-user', 'crm-supervisor', 'crm-admin'})
```
to:
```python
CRM_ROLES = frozenset({'crm-user', 'crm-supervisor', 'crm-admin', 'crm-superadmin'})
```
This is the single most important line in this task — without it, a user correctly granted `crm-superadmin` in Keycloak would have that role silently stripped by `Identity`'s role filter (`oidc.py:135`) on every login, and `require_roles(ROLE_SUPERADMIN)` (added in a later task) would never pass for anyone, ever, with no error message anywhere pointing at why.

- [ ] **Step 4: Add optional settings fields**

In `backend/app/settings.py`, add three fields to the `Settings` dataclass (near `sms_provider_url`/`sms_provider_api_key`, following that exact "unset in local dev by default" comment style):
```python
    # Keycloak Admin API access (Users & Roles, Security's password-policy display). Unset by
    # default — admin features degrade to "not configured" rather than the app failing to start;
    # see keycloak_admin.py. Real credentials come only from deploy/local/*.env, never committed.
    keycloak_admin_client_id: str = ''
    keycloak_admin_client_secret: str = ''
```
In `load_settings()`, populate them (not required, plain `.get()` with empty-string default, matching the SMS fields' exact style):
```python
        keycloak_admin_client_id=(environ.get('KEYCLOAK_ADMIN_CLIENT_ID') or '').strip(),
        keycloak_admin_client_secret=(environ.get('KEYCLOAK_ADMIN_CLIENT_SECRET') or '').strip(),
```
Add one more field, `keycloak_admin_base_url: str`, derived (not read from its own env var — no new env var needed) from the already-required `oidc_internal_base_url` (`http://keycloak:8080/auth/realms/edu-crm` in this deployment) by stripping the realm suffix:
```python
    keycloak_admin_base_url: str = ''
```
and in `load_settings()`:
```python
        keycloak_admin_base_url=environ['OIDC_INTERNAL_BASE_URL'].strip().rstrip('/').rsplit('/realms/', 1)[0],
```
(this yields `http://keycloak:8080/auth`, the server root Keycloak's Admin API lives under — `{root}/admin/realms/edu-crm/...`). This field is always populated (derived from an already-required setting) even when the admin client id/secret are empty — Task 2's client checks the id/secret specifically to decide whether it's configured, not this URL.

- [ ] **Step 5: Wire the new env var through Compose**

In `compose.yaml`'s `api` service `environment:` block, add:
```yaml
      KEYCLOAK_ADMIN_CLIENT_ID: edu-crm-admin
```
(not secret — the client id is public knowledge, only its secret is sensitive, which arrives via the existing `env_file: deploy/local/api.env`, already loaded by this service — no compose change needed for the secret itself, `generate-dev-secrets.sh` (Step 2) already writes it there).

- [ ] **Step 6: Write and run tests**

Find where `CRM_ROLES`/role-filtering is already tested (`grep -rn "CRM_ROLES\|crm-supervisor.*crm-admin" backend/tests/*.py` — likely `test_auth.py` or similar) and add:
```python
def test_crm_superadmin_role_survives_token_filtering():
    from app.oidc import CRM_ROLES
    assert 'crm-superadmin' in CRM_ROLES
```
Also add a settings test (find `backend/tests/test_settings.py` or similar):
```python
def test_keycloak_admin_settings_default_to_unconfigured():
    settings = load_settings({'DATABASE_URL': ..., 'OIDC_ISSUER': ..., ...})  # match this file's existing fixture-building pattern for a minimal valid environ
    assert settings.keycloak_admin_client_id == ''
    assert settings.keycloak_admin_client_secret == ''


def test_keycloak_admin_base_url_derived_from_internal_oidc_url():
    settings = load_settings({..., 'OIDC_INTERNAL_BASE_URL': 'http://keycloak:8080/auth/realms/edu-crm'})
    assert settings.keycloak_admin_base_url == 'http://keycloak:8080/auth'
```
Match whatever minimal-environ-building helper this test file already uses (do not hand-roll a new one). Run:
```bash
cd backend && .venv/bin/python -m pytest -q
```
(use the repo-root `.venv`, not `backend/.venv` — it doesn't exist)

- [ ] **Step 7: Validate the realm JSON**

```bash
python3 -c "import json; json.load(open('deploy/keycloak/realm-edu-crm.json')); print('valid JSON')"
```

- [ ] **Step 8: Commit**

```bash
git add deploy/keycloak/realm-edu-crm.json scripts/generate-dev-secrets.sh backend/app/oidc.py backend/app/auth.py backend/app/settings.py compose.yaml backend/tests/
git commit -m "feat(admin): add Keycloak admin client, crm-superadmin role, and settings plumbing"
```

---

### Task 2: `KeycloakAdminClient` — the real HTTP wrapper, plus its fake for tests

**Files:**
- Create: `backend/app/keycloak_admin.py`
- Modify: `backend/tests/fake_keycloak.py` (extend `FakeKeycloak` to also answer admin-API requests — additively; existing login/refresh/logout behavior must not change)
- Test: `backend/tests/test_keycloak_admin.py` (new)

**Interfaces:**
- Consumes: `Settings.keycloak_admin_client_id/_secret/_base_url` (Task 1).
- Produces: `KeycloakAdminClient(base_url, client_id, client_secret, http_client)` with methods `is_configured() -> bool`, `find_user_by_email(email) -> AdminUser | None`, `list_users(*, query='') -> list[AdminUser]`, `assign_realm_role(user_id, role_name) -> None`, `remove_realm_role(user_id, role_name) -> None`, `count_users_with_role(role_name) -> int`, `get_password_policy() -> str`. Raises `KeycloakAdminError` (or `KeycloakAdminUnavailable` for connectivity/5xx, mirroring `oidc.py`'s `OIDCError`/`OIDCUnavailable` split) on failure — callers decide how to degrade. Task 4's bootstrap script and later slices (5: Безопасность, 6: Пользователи и роли) both depend on this exact interface.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_keycloak_admin.py`:
```python
import pytest

from app.keycloak_admin import KeycloakAdminClient, KeycloakAdminError, KeycloakAdminUnavailable
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET, FakeKeycloak


def make_client(fake):
    return KeycloakAdminClient(
        base_url=ADMIN_BASE_URL, client_id=ADMIN_CLIENT_ID, client_secret=ADMIN_CLIENT_SECRET,
        http_client=fake.http_client(),
    )


def test_is_configured_true_with_credentials():
    assert make_client(FakeKeycloak()).is_configured() is True


def test_is_configured_false_without_credentials():
    client = KeycloakAdminClient(base_url='', client_id='', client_secret='', http_client=FakeKeycloak().http_client())
    assert client.is_configured() is False


def test_find_user_by_email_found():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='anna@demo.local', username='anna', roles=['crm-user'])
    user = make_client(fake).find_user_by_email('anna@demo.local')
    assert user is not None
    assert user.id == 'u1'
    assert user.roles == ['crm-user']


def test_find_user_by_email_not_found():
    fake = FakeKeycloak()
    assert make_client(fake).find_user_by_email('nobody@demo.local') is None


def test_list_users_returns_all():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-user'])
    fake.add_admin_user(id='u2', email='b@demo.local', username='b', roles=[])
    users = make_client(fake).list_users()
    assert {u.id for u in users} == {'u1', 'u2'}


def test_assign_realm_role_adds_it():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=[])
    make_client(fake).assign_realm_role('u1', 'crm-superadmin')
    assert fake.admin_users['u1']['roles'] == ['crm-superadmin']


def test_remove_realm_role_removes_it():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-superadmin', 'crm-admin'])
    make_client(fake).remove_realm_role('u1', 'crm-superadmin')
    assert fake.admin_users['u1']['roles'] == ['crm-admin']


def test_count_users_with_role():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-superadmin'])
    fake.add_admin_user(id='u2', email='b@demo.local', username='b', roles=['crm-user'])
    assert make_client(fake).count_users_with_role('crm-superadmin') == 1


def test_get_password_policy():
    fake = FakeKeycloak()
    fake.realm_password_policy = "length(12) and notUsername"
    assert make_client(fake).get_password_policy() == "length(12) and notUsername"


def test_wrong_admin_credentials_raise():
    fake = FakeKeycloak()
    client = KeycloakAdminClient(base_url=ADMIN_BASE_URL, client_id=ADMIN_CLIENT_ID, client_secret='wrong', http_client=fake.http_client())
    with pytest.raises(KeycloakAdminError):
        client.list_users()


def test_keycloak_unavailable_raises_unavailable():
    fake = FakeKeycloak()
    fake.unavailable = True
    with pytest.raises(KeycloakAdminUnavailable):
        make_client(fake).list_users()
```

- [ ] **Step 2: Run it, confirm it fails (module doesn't exist yet)**

```bash
cd backend && .venv/bin/python -m pytest tests/test_keycloak_admin.py -v
```

- [ ] **Step 3: Extend `FakeKeycloak` additively**

In `backend/tests/fake_keycloak.py`, add near the top (alongside the existing `ISSUER`/`CLIENT_ID`/`CLIENT_SECRET` constants):
```python
ADMIN_BASE_URL = 'http://keycloak.test/auth'
ADMIN_CLIENT_ID = 'edu-crm-admin'
ADMIN_CLIENT_SECRET = 'test-admin-secret'
```
In `FakeKeycloak.__init__`, add:
```python
        self.admin_users = {}  # id -> {"id", "email", "username", "roles": [...]}
        self.realm_password_policy = "length(12) and notUsername and notEmail and passwordHistory(3)"
```
Add these new methods to `FakeKeycloak`:
```python
    def add_admin_user(self, *, id, email, username, roles):
        self.admin_users[id] = {'id': id, 'email': email, 'username': username, 'roles': list(roles)}
```
Now extend `handler()`. The existing method starts with the JWKS check, then unconditionally parses `request.content` as form data and checks `client_id`/`client_secret` against the OIDC login client's constants for every other path — this must become conditional so it doesn't break admin-API requests (which use a different client and, for GET requests, carry no form body at all). Restructure the start of `handler()` like this (keep everything below the JWKS check that already exists, unchanged):

```python
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
        if path.startswith('/auth/admin/realms/edu-crm/'):
            return self._admin_handler(request, path)

        # (everything below this point is the existing OIDC login/refresh/logout handling, unchanged)
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        ...
```
(`...` marks the rest of the existing method body — copy it verbatim, do not modify it.)

Add the new `_admin_handler`:
```python
    def _admin_handler(self, request, path):
        suffix = path[len('/auth/admin/realms/edu-crm/'):]
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
            import json as _json
            roles = _json.loads(request.content)
            user = self.admin_users.get(user_id)
            if user is None:
                return httpx.Response(404)
            names = {r['name'] for r in roles}
            if request.method == 'POST':
                user['roles'] = list(set(user['roles']) | names)
            else:
                user['roles'] = [r for r in user['roles'] if r not in names]
            return httpx.Response(204)
        if suffix.startswith('users/') and suffix.endswith('/role-mappings/realm') and request.method == 'GET':
            user_id = suffix[len('users/'):-len('/role-mappings/realm')]
            user = self.admin_users.get(user_id)
            if user is None:
                return httpx.Response(404)
            return httpx.Response(200, json=[{'id': r, 'name': r} for r in user['roles']])
        if suffix == '' and request.method == 'GET':
            return httpx.Response(200, json={'passwordPolicy': self.realm_password_policy})
        return httpx.Response(404)
```
This is a starting sketch for the fake, not gospel — if `KeycloakAdminClient`'s real request shapes (Step 4) end up slightly different from what this fake expects (e.g. a different way of looking up a role's id before assigning it — Keycloak's real role-mappings POST body needs each role's `id`, not just its `name`, which means a real client typically does a `GET .../roles/{role-name}` first to resolve the id), adjust the fake to match reality rather than simplifying reality to match the fake. Get this right — a fake that's wrong in a way that happens to make tests pass is worse than no fake.

- [ ] **Step 4: Implement `KeycloakAdminClient`**

`backend/app/keycloak_admin.py`, styled like `backend/app/oidc.py` (dataclass-free simple class, `httpx` client injected, clear `Error`/`Unavailable` exception split):
```python
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
    """Keycloak rejected the request (bad credentials, not found, etc)."""


class KeycloakAdminUnavailable(KeycloakAdminError):
    """Keycloak could not be reached or answered with a server error."""


class AdminUser:
    def __init__(self, id, email, username, roles):
        self.id = id
        self.email = email
        self.username = username
        self.roles = roles


class KeycloakAdminClient:
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

    def _admin_token(self):
        now = time.monotonic()
        if self._token and now < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token
        try:
            response = self._http.post(
                f'{self._base_url}/realms/edu-crm/protocol/openid-connect/token',
                data={'grant_type': 'client_credentials', 'client_id': self._client_id, 'client_secret': self._client_secret},
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

    def find_user_by_email(self, email):
        response = self._request('GET', '/users', params={'email': email, 'exact': 'true'})
        rows = response.json()
        if not rows:
            return None
        row = rows[0]
        return AdminUser(id=row['id'], email=row.get('email', ''), username=row.get('username', ''), roles=self._realm_roles_of(row['id']))

    def list_users(self):
        response = self._request('GET', '/users')
        return [
            AdminUser(id=row['id'], email=row.get('email', ''), username=row.get('username', ''), roles=self._realm_roles_of(row['id']))
            for row in response.json()
        ]

    def _realm_roles_of(self, user_id):
        response = self._request('GET', f'/users/{user_id}/role-mappings/realm')
        return [row['name'] for row in response.json()]

    def _role_id(self, role_name):
        if role_name not in self._role_id_cache:
            response = self._request('GET', f'/roles/{role_name}')
            self._role_id_cache[role_name] = response.json()['id']
        return self._role_id_cache[role_name]

    def assign_realm_role(self, user_id, role_name):
        self._request('POST', f'/users/{user_id}/role-mappings/realm', json=[{'id': self._role_id(role_name), 'name': role_name}])

    def remove_realm_role(self, user_id, role_name):
        self._request('DELETE', f'/users/{user_id}/role-mappings/realm', json=[{'id': self._role_id(role_name), 'name': role_name}])

    def count_users_with_role(self, role_name):
        return sum(1 for u in self.list_users() if role_name in u.roles)

    def get_password_policy(self):
        response = self._request('GET', '')
        return response.json().get('passwordPolicy', '')
```
This calls `GET /roles/{role_name}` to resolve a role's id before assigning/removing it — if your fake (Step 3) doesn't yet answer that path, add it there (`suffix == f'roles/{name}'` → `{'id': name, 'name': name}` is a fine fake response shape, using the name as a stand-in id since the fake never needs a real UUID).

- [ ] **Step 5: Run the tests, confirm they pass; run the full backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/test_keycloak_admin.py -v
cd backend && .venv/bin/python -m pytest -q
```
Pay close attention to any OTHER existing test that uses `FakeKeycloak` — the `handler()` restructuring in Step 3 must not change behavior for the existing login/refresh/logout paths. If anything regresses, the restructuring broke something; fix the restructuring, not the pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/keycloak_admin.py backend/tests/fake_keycloak.py backend/tests/test_keycloak_admin.py
git commit -m "feat(admin): add KeycloakAdminClient and its test fake"
```

---

### Task 3: Grant the service account its real permissions on the live realm

**Files:**
- Create: `scripts/keycloak-grant-admin-permissions.sh`
- Modify: `docs/decisions.md` (record why this is a live-`kcadm` step, not realm-JSON, mirroring the existing D-entry for `keycloak-add-public-origin.sh` if one exists — check first)

**Interfaces:**
- Consumes: the `edu-crm-admin` client from Task 1 (must already exist in the running realm — i.e., this script runs against a Keycloak that has re-imported or already has this client; if the realm was imported before Task 1's JSON changes, the client won't exist yet and this script's own error message must make that obvious, not fail cryptically).
- Produces: the `service-account-edu-crm-admin` user granted `view-users`, `manage-users`, `view-realm` on the `realm-management` client. Task 2's `KeycloakAdminClient`, once real credentials are in `deploy/local/*.env` and this script has run, becomes genuinely functional against the dev stack (not just the fake).

- [ ] **Step 1: Write the script**

Mirror `scripts/keycloak-add-public-origin.sh`'s exact structure and error-handling style:
```bash
#!/usr/bin/env bash
# Grants the edu-crm-admin service account the least-privilege realm-management permissions the
# CRM's Keycloak Admin integration needs: listing users, assigning/removing realm roles, and
# reading the realm's password policy. Run once after the edu-crm-admin client exists in the
# running realm (deploy/keycloak/realm-edu-crm.json) — safe to re-run (kcadm add-roles is
# idempotent per role).
set -euo pipefail
cd "$(dirname "$0")/.."

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password"

service_account_username="service-account-edu-crm-admin"
if ! docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get users -r edu-crm \
    --query "username=$service_account_username" --fields id --format csv --noquotes | grep -q .; then
  echo "edu-crm-admin's service account user not found — is the client in the running realm yet?" >&2
  echo "If the realm was imported before this client was added to realm-edu-crm.json, you need to" >&2
  echo "add it to the live realm first (Keycloak admin console, or re-import into a fresh volume)." >&2
  exit 1
fi

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh add-roles -r edu-crm \
  --uusername "$service_account_username" --cclientid realm-management \
  --rolename view-users --rolename manage-users --rolename view-realm

echo "Granted view-users, manage-users, view-realm to $service_account_username."
```

- [ ] **Step 2: Run it against the dev stack and verify**

```bash
chmod +x scripts/keycloak-grant-admin-permissions.sh
```
If the running Keycloak container doesn't yet have the `edu-crm-admin` client (likely — the realm was imported before Task 1's JSON change and Keycloak's `--import-realm` skips already-existing realms), this script will correctly fail with the message above. In that case, do not attempt to force a re-import (would risk realm data). Instead, add the client to the live realm the same way `scripts/keycloak-add-public-origin.sh` demonstrated for a client attribute change — but a whole new client is a bigger live change than a single attribute edit, so use `kcadm create clients` directly:
```bash
docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh create clients -r edu-crm \
  -s clientId=edu-crm-admin -s 'secret=$(the value of EDU_CRM_ADMIN_CLIENT_SECRET from deploy/local/keycloak.env, after running scripts/generate-dev-secrets.sh regenerate logic — see note below)' \
  -s enabled=true -s protocol=openid-connect -s publicClient=false -s standardFlowEnabled=false \
  -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s serviceAccountsEnabled=true \
  -s fullScopeAllowed=false
```
Note: `generate-dev-secrets.sh` never overwrites existing secret files (checked at its own top) — if `deploy/local/keycloak.env`/`api.env` already exist from before this plan, Task 1's Step 2 change to that script won't retroactively add `EDU_CRM_ADMIN_CLIENT_SECRET` to them. Handle this practically: either move the two files aside and regenerate (acceptable in local dev — it invalidates other secrets too, ask before doing this in case the owner wants to avoid disrupting a running demo), or manually generate one value (`openssl rand -base64 40 | tr -dc 'A-Za-z0-9' | head -c 40`) and append it to both files by hand with the correct variable names, matching Task 1's Step 2 exactly. Prefer asking the owner which they'd like rather than silently picking one — this touches the same secrets Task 1 already made a design decision about, but the *operational* choice of regenerate-vs-append is a live-environment change worth a quick confirmation.
Then re-run this task's Step 1 script and confirm it succeeds.

- [ ] **Step 3: Record the decision**

Add a `docs/decisions.md` entry (check the current highest `D-` number first) documenting: why the service-account role grant is done live via `kcadm` rather than realm-export JSON (fragile to hand-write correctly; this repo already has a proven pattern for exactly this from the Cloudflare deployment work), and the exact least-privilege role set granted (`view-users`, `manage-users`, `view-realm` — explicitly not `manage-realm`/`manage-clients`/anything broader).

- [ ] **Step 4: Commit**

```bash
git add scripts/keycloak-grant-admin-permissions.sh docs/decisions.md
git commit -m "feat(admin): grant edu-crm-admin its least-privilege realm-management permissions"
```

---

### Task 4: Deterministic superadmin bootstrap

**Files:**
- Create: `backend/app/bootstrap_superadmin.py`
- Modify: `backend/docker-entrypoint.sh`
- Modify: `.env.example` or wherever other optional env vars are documented (check `README.md`'s existing env var documentation pattern)
- Test: `backend/tests/test_bootstrap_superadmin.py` (new)

**Interfaces:**
- Consumes: `KeycloakAdminClient` (Task 2), `Settings` (Task 1), a new optional `INITIAL_SUPERADMIN_EMAIL` env var.
- Produces: a standalone script runnable as `python -m app.bootstrap_superadmin`, idempotent, never raises past its own `main()` (always exits 0), logs clearly in every outcome (configured-and-applied, configured-but-already-has-superadmin, configured-but-email-not-found, not-configured-skipping, keycloak-unavailable). `count_users_with_role` (Task 2) is the primitive later slices (6: Пользователи и роли) reuse to enforce "never remove the last superadmin" at the point role edits actually happen — that enforcement itself is NOT built here, only the counting primitive this bootstrap already needs for itself.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bootstrap_superadmin.py`:
```python
import logging

from app.bootstrap_superadmin import bootstrap_superadmin
from app.keycloak_admin import KeycloakAdminClient
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET, FakeKeycloak


def make_client(fake):
    return KeycloakAdminClient(base_url=ADMIN_BASE_URL, client_id=ADMIN_CLIENT_ID, client_secret=ADMIN_CLIENT_SECRET, http_client=fake.http_client())


def test_grants_superadmin_to_the_configured_email_when_none_exists():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='owner@demo.local', username='owner', roles=['crm-admin'])
    client = make_client(fake)
    bootstrap_superadmin(client, email='owner@demo.local')
    assert 'crm-superadmin' in fake.admin_users['u1']['roles']


def test_does_nothing_when_a_superadmin_already_exists():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='existing@demo.local', username='existing', roles=['crm-superadmin'])
    fake.add_admin_user(id='u2', email='owner@demo.local', username='owner', roles=['crm-admin'])
    client = make_client(fake)
    bootstrap_superadmin(client, email='owner@demo.local')
    assert 'crm-superadmin' not in fake.admin_users['u2']['roles']
    assert fake.admin_users['u1']['roles'] == ['crm-superadmin']


def test_logs_and_does_not_raise_when_email_not_found(caplog):
    fake = FakeKeycloak()
    client = make_client(fake)
    with caplog.at_level(logging.WARNING):
        bootstrap_superadmin(client, email='nobody@demo.local')  # must not raise
    assert 'not found' in caplog.text.lower()


def test_logs_and_does_not_raise_when_keycloak_unavailable(caplog):
    fake = FakeKeycloak()
    fake.unavailable = True
    client = make_client(fake)
    with caplog.at_level(logging.WARNING):
        bootstrap_superadmin(client, email='owner@demo.local')  # must not raise
    assert caplog.text  # something was logged


def test_skips_cleanly_when_email_not_configured(caplog):
    fake = FakeKeycloak()
    client = make_client(fake)
    with caplog.at_level(logging.INFO):
        bootstrap_superadmin(client, email='')
    assert 'not configured' in caplog.text.lower() or 'skip' in caplog.text.lower()


def test_skips_cleanly_when_admin_client_not_configured(caplog):
    client = KeycloakAdminClient(base_url='', client_id='', client_secret='', http_client=FakeKeycloak().http_client())
    with caplog.at_level(logging.INFO):
        bootstrap_superadmin(client, email='owner@demo.local')  # must not raise despite client being unconfigured
```

- [ ] **Step 2: Run it, confirm it fails**

```bash
cd backend && .venv/bin/python -m pytest tests/test_bootstrap_superadmin.py -v
```

- [ ] **Step 3: Implement**

`backend/app/bootstrap_superadmin.py`:
```python
"""Deterministically ensures exactly one superadmin exists, idempotently, without ever removing
one. Run as a docker-entrypoint.sh step on every container start (see that file) — never wired
into create_app()/lifespan, so it can never fire during the test suite by accident.

Never raises past bootstrap_superadmin() or main() — a misconfigured or briefly-unreachable
Keycloak must not block the API from starting; every outcome is logged instead.
"""
import logging
import os

from .keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from .settings import load_settings
import httpx

logger = logging.getLogger(__name__)

SUPERADMIN_ROLE = 'crm-superadmin'


def bootstrap_superadmin(client, *, email):
    if not client.is_configured():
        logger.info('Keycloak admin client not configured — skipping superadmin bootstrap.')
        return
    if not email:
        logger.info('INITIAL_SUPERADMIN_EMAIL not set — skipping superadmin bootstrap.')
        return
    try:
        if client.count_users_with_role(SUPERADMIN_ROLE) > 0:
            logger.info('A superadmin already exists — nothing to do.')
            return
        user = client.find_user_by_email(email)
        if user is None:
            logger.warning('INITIAL_SUPERADMIN_EMAIL (%s) matches no Keycloak user — not found, skipping.', email)
            return
        client.assign_realm_role(user.id, SUPERADMIN_ROLE)
        logger.info('Granted crm-superadmin to %s (bootstrap).', email)
    except KeycloakAdminError as error:
        logger.warning('Superadmin bootstrap could not complete (%s) — continuing startup anyway.', error)


def main():
    settings = load_settings()
    client = KeycloakAdminClient(
        base_url=settings.keycloak_admin_base_url,
        client_id=settings.keycloak_admin_client_id,
        client_secret=settings.keycloak_admin_client_secret,
        http_client=httpx.Client(timeout=10),
    )
    bootstrap_superadmin(client, email=(os.environ.get('INITIAL_SUPERADMIN_EMAIL') or '').strip())


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Wire into the entrypoint**

In `backend/docker-entrypoint.sh`, add a new line after `python -m app.db_migrate` (bootstrap doesn't need demo data, so ordering relative to the `SEED_DEMO` block doesn't matter — put it right after migrations for clarity):
```sh
python -m app.db_migrate
python -m app.bootstrap_superadmin
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed
fi
exec "$@"
```
Do not add `set +e` around this line or otherwise suppress a real crash in `main()` itself — `bootstrap_superadmin()`'s own internal try/except already ensures it never raises for a *configuration* or *connectivity* reason; if `main()` still crashes (e.g. `load_settings()` itself fails because a genuinely required setting is missing), that's a real, pre-existing startup problem this script correctly surfaces, not something to swallow further.

- [ ] **Step 5: Document the new env var**

Find how `SMS_PROVIDER_URL`/other optional settings are documented (check `README.md`, `.env.example`) and add `INITIAL_SUPERADMIN_EMAIL` there with the same brief style — an optional var, unset by default, used once at container startup to grant the first `crm-superadmin` to a matching Keycloak user if none exists yet.

- [ ] **Step 6: Run the tests, confirm they pass; run the full backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/test_bootstrap_superadmin.py -v
cd backend && .venv/bin/python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/bootstrap_superadmin.py backend/docker-entrypoint.sh backend/tests/test_bootstrap_superadmin.py README.md
git commit -m "feat(admin): deterministic, idempotent superadmin bootstrap at container start"
```

## Self-Review Notes

- **Spec coverage:** Keycloak Admin API integration with backend service-account (Tasks 1-3) ✓. Credentials never reach the frontend / env-only / never committed (Task 1 — new secret follows the exact existing gitignored-`deploy/local/*.env` pattern) ✓. Least-privilege service account (Task 3 — exactly `view-users`/`manage-users`/`view-realm`, explicitly not broader) ✓. Clear `crm-superadmin` role protecting admin/system endpoints (Task 1 — the role exists and survives token filtering; actual endpoint-level `require_roles(ROLE_SUPERADMIN)` gating is added by the slices that build those endpoints — 5: Безопасность, 6: Пользователи и роли, 7: Резервное копирование — not this plan, which only builds the role and the client that can grant it) ✓. Deterministic/configurable initial superadmin via deployment config (Task 4 — `INITIAL_SUPERADMIN_EMAIL`) ✓. Never end up with zero superadmins from this process (Task 4 only ever adds, never removes; the counting primitive other slices need for their own removal-guard is built and tested here) ✓. No large RBAC/permission editor (nothing in this plan builds one — just one role, one client) ✓. Pending registrations = Keycloak users without the CRM role (this plan provides `list_users()`/roles per user, the primitive slice 6 needs; the UI itself is slice 6, not here) ✓.
- **Placeholder scan:** no TBD/"add later" instructions left unfollowed; every code block is complete. Task 3 Step 2's live-`kcadm create clients` fallback path has an inline placeholder-looking `$(...)` in the shown command specifically because the real secret value can't be known at plan-writing time — this is flagged explicitly as something requiring a real decision (regenerate vs. hand-append) at execution time, not a lazy omission.
- **Type/name consistency:** `KeycloakAdminClient`'s constructor signature (`base_url`, `client_id`, `client_secret`, `http_client`) is identical across Task 2's definition, its own tests, and Task 4's `bootstrap_superadmin.py` usage. `ADMIN_BASE_URL`/`ADMIN_CLIENT_ID`/`ADMIN_CLIENT_SECRET` fake-test constants are the same across Task 2 and Task 4's test files. `SUPERADMIN_ROLE = 'crm-superadmin'` (Task 4) matches `ROLE_SUPERADMIN` (Task 1, `auth.py`) and the realm role name (Task 1, realm JSON) exactly — same literal string everywhere.
