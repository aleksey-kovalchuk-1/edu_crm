#!/bin/sh
# Applies database migrations before the API starts, so the schema always matches the code.
set -e
python -m app.db_migrate
exec "$@"
