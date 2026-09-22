"""Deterministically ensures exactly one superadmin exists, idempotently, without ever removing
one. Run as a docker-entrypoint.sh step on every container start (see that file) — never wired
into create_app()/lifespan, so it can never fire during the test suite by accident.

Never raises past bootstrap_superadmin() or main() — a misconfigured or briefly-unreachable
Keycloak must not block the API from starting; every outcome is logged instead.

On a fresh `docker compose up`, this step can run before Keycloak (whose healthcheck allows a
90s start_period) is actually reachable, and the `api` container is deliberately not made to
depend on `keycloak` being healthy (see compose.yaml) — so instead of giving up on the first
KeycloakAdminUnavailable, bootstrap_superadmin() retries a few times over a short, bounded window
before falling back to today's "log and continue" behavior.
"""
import logging
import os
import time

import httpx

from .keycloak_admin import KeycloakAdminClient, KeycloakAdminError, KeycloakAdminUnavailable
from .settings import load_settings

logger = logging.getLogger(__name__)

SUPERADMIN_ROLE = 'crm-superadmin'
RETRY_INTERVAL_SECONDS = 5
RETRY_TIMEOUT_SECONDS = 60


def _grant_if_needed(client, email):
    if client.count_users_with_role(SUPERADMIN_ROLE) > 0:
        logger.info('A superadmin already exists — nothing to do.')
        return
    user = client.find_user_by_email(email)
    if user is None:
        logger.warning('INITIAL_SUPERADMIN_EMAIL (%s) matches no Keycloak user — not found, skipping.', email)
        return
    client.assign_realm_role(user.id, SUPERADMIN_ROLE)
    logger.info('Granted crm-superadmin to %s (bootstrap).', email)


def bootstrap_superadmin(
    client, *, email,
    sleep=time.sleep, retry_interval=RETRY_INTERVAL_SECONDS, retry_timeout=RETRY_TIMEOUT_SECONDS,
):
    if not client.is_configured():
        logger.info('Keycloak admin client not configured — skipping superadmin bootstrap.')
        return
    if not email:
        logger.info('INITIAL_SUPERADMIN_EMAIL not set — skipping superadmin bootstrap.')
        return

    elapsed = 0.0
    while True:
        try:
            _grant_if_needed(client, email)
            return
        except KeycloakAdminUnavailable as error:
            if elapsed >= retry_timeout:
                logger.warning(
                    'Superadmin bootstrap gave up after retrying for ~%ss (%s) — continuing startup anyway.',
                    elapsed, error,
                )
                return
            logger.info('Keycloak not reachable yet (%s) — retrying in %ss.', error, retry_interval)
            sleep(retry_interval)
            elapsed += retry_interval
        except KeycloakAdminError as error:
            logger.warning('Superadmin bootstrap could not complete (%s) — continuing startup anyway.', error)
            return


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
