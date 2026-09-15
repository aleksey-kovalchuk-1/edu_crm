#!/bin/sh
# Prepares the database before the API starts: migrations first, then optional demo data.
# Seeding runs here, once, rather than inside each server worker, so parallel workers cannot seed twice.
set -e
python -m app.db_migrate
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed
fi
exec "$@"
