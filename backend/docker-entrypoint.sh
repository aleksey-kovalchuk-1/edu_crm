#!/bin/sh
# Prepares the database before the process starts: migrations first, then optional demo data.
# Seeding runs here, once, rather than inside each server worker, so parallel workers cannot seed twice.
# SKIP_MIGRATE lets a second container sharing this image and database (the background-job `worker`
# service, compose.yaml) skip a concurrent, unlocked `alembic upgrade head` race against the API
# container's own migration; it waits for the API to be healthy (which implies migrated) instead.
set -e
if [ "${SKIP_MIGRATE:-false}" != "true" ]; then
  python -m app.db_migrate
fi
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed
fi
exec "$@"
