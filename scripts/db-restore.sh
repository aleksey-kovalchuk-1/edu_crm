#!/usr/bin/env bash
# Decrypts a dump into a NEW database and prints its row counts.
# It refuses to use a database name that already exists, so live data is never overwritten.
set -euo pipefail
set +x
umask 077
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
if [[ "$dump" != *.dump.age ]]; then
  echo 'expected an encrypted .dump.age file' >&2; exit 2
fi
command -v age >/dev/null || { echo 'age is required' >&2; exit 2; }
if [[ -z "${BACKUP_AGE_IDENTITY_FILE:-}" || ! -f "$BACKUP_AGE_IDENTITY_FILE" || ! -r "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  echo 'BACKUP_AGE_IDENTITY_FILE must point to a readable identity' >&2; exit 2
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

age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$dump" | docker compose exec -T db pg_restore --list >/dev/null
created=0
cleanup() {
  if [[ "$created" == 1 ]]; then
    docker compose exec -T db dropdb -U "$DB_USER" "$target" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
docker compose exec -T db createdb -U "$DB_USER" "$target"
created=1
age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$dump" | docker compose exec -T db pg_restore -U "$DB_USER" -d "$target" --no-owner --exit-on-error
"$(dirname "$0")/db-row-counts.sh" "$target"
created=0
