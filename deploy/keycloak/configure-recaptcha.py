#!/usr/bin/env python3
"""Idempotent post-boot job: sets the reCAPTCHA v2 site/secret key on the registration flow's
reCAPTCHA execution through Keycloak's Admin REST API.

Why this exists instead of a plain realm-import value (see docs/decisions.md D-158): the registration flow
copy in realm-edu-crm.json marks the reCAPTCHA execution REQUIRED, but its per-execution authenticatorConfig
(site key, secret key) is not reliably set by ${VAR} substitution inside a nested authenticationFlows
execution on Keycloak 26.7.3 -- so this job sets it once, after Keycloak is healthy, the same way an
administrator would in the console. Safe to re-run: it updates the existing config in place if one already
exists instead of creating a duplicate.

Run as the `keycloak-recaptcha-init` Compose service (see compose.yaml), which waits for
`keycloak: condition: service_healthy` and never needs to run again unless the keys change.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REALM = 'edu-crm'
FLOW_ALIAS = 'registration-with-recaptcha form'
PROVIDER_ID = 'registration-recaptcha-action'
CONFIG_ALIAS = 'edu-crm-recaptcha'


def env(name):
    value = (os.environ.get(name) or '').strip()
    if not value:
        print(f'{name} is not set', file=sys.stderr)
        sys.exit(1)
    return value


def request(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
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
    site_key = env('RECAPTCHA_SITE_KEY')
    secret_key = env('RECAPTCHA_SECRET_KEY')

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
    quoted_flow = urllib.parse.quote(FLOW_ALIAS)
    status, executions = request('GET', f'{admin}/authentication/flows/{quoted_flow}/executions', token=token)
    if status != 200:
        print(f'Cannot list executions of flow {FLOW_ALIAS!r}: HTTP {status} {executions}', file=sys.stderr)
        print('Realm import may not have created it yet -- check the keycloak container logs.', file=sys.stderr)
        sys.exit(1)

    recaptcha = next((execution for execution in executions if execution.get('providerId') == PROVIDER_ID), None)
    if recaptcha is None:
        print(f'No {PROVIDER_ID!r} execution found in flow {FLOW_ALIAS!r}', file=sys.stderr)
        sys.exit(1)

    config = {
        'alias': CONFIG_ALIAS,
        'config': {
            'site.key': site_key,
            'secret.key': secret_key,
            'action': 'register',
            'useRecaptchaNet': 'false',
            'recaptcha.v3': 'false',
        },
    }

    existing_config_id = recaptcha.get('authenticationConfig')
    if existing_config_id:
        status, body = request('PUT', f'{admin}/authentication/config/{existing_config_id}', token=token,
                                body={**config, 'id': existing_config_id})
        action = 'updated'
    else:
        status, body = request('POST', f'{admin}/authentication/executions/{recaptcha["id"]}/config', token=token,
                                body=config)
        action = 'created'

    if status not in (200, 201, 204):
        print(f'Failed to set reCAPTCHA config ({action}): HTTP {status} {body}', file=sys.stderr)
        sys.exit(1)

    print(f'reCAPTCHA config {action} for execution {recaptcha["id"]} (site key ...{site_key[-6:]})')


if __name__ == '__main__':
    main()
