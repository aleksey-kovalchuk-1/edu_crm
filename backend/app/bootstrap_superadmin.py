"""Deterministically ensures exactly one superadmin exists, idempotently, without ever removing
one. Run as a docker-entrypoint.sh step on every container start (see that file) — never wired
into create_app()/lifespan, so it can never fire during the test suite by accident.

Never raises past bootstrap_superadmin() or main() — a misconfigured or briefly-unreachable
Keycloak must not block the API from starting; every outcome is logged instead.
"""
import logging
import os

import httpx

from .keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from .settings import load_settings

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
