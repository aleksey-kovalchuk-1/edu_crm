#!/usr/bin/env python3
"""Idempotent post-boot job: adds crm-user to the composites of the realm's default role
(default-roles-edu-crm), so every newly created account -- self-registered or admin-created without
explicit roles -- starts with basic CRM access. crm-supervisor and crm-admin are never added here and
must be assigned explicitly (docs/decisions.md D-157).

Why this is not done by realm-import instead: verified empirically against Keycloak 26.7.3 that a
"composites" list on a realm-import roles[] entry whose name matches the realm's already-autocreated
default role (default-roles-edu-crm) is silently ignored -- the role exists before the roles[] array is
processed, and re-declaring it there does not merge in new composites. A plain Admin REST API call
(exactly what an administrator would do by hand in the console) does work and is idempotent -- running
this repeatedly is harmless, it only adds the role if not already present.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REALM = 'edu-crm'
ROLE_TO_ADD = 'crm-user'
# See deploy/keycloak/configure-recaptcha.py for why this wait is needed: the healthcheck can flip
# healthy slightly before a *fresh* realm import finishes.
READY_RETRIES = 24
READY_DELAY_SECONDS = 5


def wait_for_realm(base_url):
    url = f'{base_url}/realms/{REALM}/.well-known/openid-configuration'
    for attempt in range(1, READY_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError) as error:
            if attempt == READY_RETRIES:
                print(f'Realm {REALM!r} never became reachable at {url}: {error}', file=sys.stderr)
                sys.exit(1)
        time.sleep(READY_DELAY_SECONDS)


def env(name):
    value = (os.environ.get(name) or '').strip()
    if not value:
        print(f'{name} is not set', file=sys.stderr)
        sys.exit(1)
    return value


def request(method, url, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Authorization': f'Bearer {token}'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, (json.loads(raw) if raw else None)


def main():
    base_url = (os.environ.get('KEYCLOAK_INTERNAL_BASE_URL') or 'http://keycloak:8080/auth').rstrip('/')
    admin_user = env('KC_BOOTSTRAP_ADMIN_USERNAME')
    admin_password = env('KC_BOOTSTRAP_ADMIN_PASSWORD')

    wait_for_realm(base_url)
    token_body = urllib.parse.urlencode({
        'client_id': 'admin-cli', 'grant_type': 'password', 'username': admin_user, 'password': admin_password,
    }).encode()
    req = urllib.request.Request(
        f'{base_url}/realms/master/protocol/openid-connect/token', data=token_body, method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        token = json.load(response)['access_token']

    admin = f'{base_url}/admin/realms/{REALM}'
    status, realm_rep = request('GET', admin, token)
    if status != 200:
        print(f'Cannot read realm {REALM!r}: HTTP {status} {realm_rep}', file=sys.stderr)
        sys.exit(1)
    default_role_id = realm_rep['defaultRole']['id']

    status, composites = request('GET', f'{admin}/roles-by-id/{default_role_id}/composites', token)
    if status != 200:
        print(f'Cannot read composites of the default role: HTTP {status} {composites}', file=sys.stderr)
        sys.exit(1)
    if any(role['name'] == ROLE_TO_ADD for role in composites):
        print(f'{ROLE_TO_ADD!r} is already a composite of the default role; nothing to do')
        return

    status, role_rep = request('GET', f'{admin}/roles/{ROLE_TO_ADD}', token)
    if status != 200:
        print(f'Cannot read role {ROLE_TO_ADD!r}: HTTP {status} {role_rep}', file=sys.stderr)
        sys.exit(1)

    status, body = request('POST', f'{admin}/roles-by-id/{default_role_id}/composites', token, body=[role_rep])
    if status not in (200, 204):
        print(f'Failed to add {ROLE_TO_ADD!r} to the default role: HTTP {status} {body}', file=sys.stderr)
        sys.exit(1)
    print(f'Added {ROLE_TO_ADD!r} to the composites of default-roles-{REALM}')


if __name__ == '__main__':
    main()
