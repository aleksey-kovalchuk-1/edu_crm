#!/usr/bin/env bash
# Restores a dump into a NEW database and prints its row counts.
# It refuses to use a database name that already exists, so live data is never overwritten.
set -euo pipefail
cd "$(dirname "$0")/.."

DB_USER="${DB_USER:-crm}"

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <dump-file> <new-database-name>" >&2
  exit 2
fi
dump="$1"
target="$2"

if [[ ! -f "$dump" ]]; then
  echo "dump not found: $dump" >&2
  exit 2
fi
# The name is interpolated into SQL below; the pattern rules out quoting tricks.
if [[ ! "$target" =~ ^[a-z_][a-z0-9_]*$ ]]; then
  echo "database name must match [a-z_][a-z0-9_]*" >&2
  exit 2
fi

exists="$(docker compose exec -T db psql -U "$DB_USER" -d postgres -Atc "select 1 from pg_database where datname = '$target'")"
if [[ -n "$exists" ]]; then
  echo "database '$target' already exists; choose a new name" >&2
  exit 1
fi

docker compose exec -T db createdb -U "$DB_USER" "$target"
docker compose exec -T db pg_restore -U "$DB_USER" -d "$target" --no-owner --exit-on-error < "$dump"
"$(dirname "$0")/db-row-counts.sh" "$target"
