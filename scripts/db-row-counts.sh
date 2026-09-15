#!/usr/bin/env bash
# Prints exact row counts for every table in the public schema of one database.
# Used to compare a live database with a restored copy.
set -euo pipefail
cd "$(dirname "$0")/.."

DB_USER="${DB_USER:-crm}"
target="${1:-edu_crm}"

if [[ ! "$target" =~ ^[a-z_][a-z0-9_]*$ ]]; then
  echo "database name must match [a-z_][a-z0-9_]*" >&2
  exit 2
fi

docker compose exec -T db psql -U "$DB_USER" -d "$target" -Atc "
  select table_name,
         (xpath('/row/c/text()',
                query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name),
                             false, true, '')))[1]::text::bigint
  from information_schema.tables
  where table_schema = 'public' and table_type = 'BASE TABLE'
  order by table_name"
