#!/usr/bin/env bash
# Creates a custom-format pg_dump of the Compose database outside the repository.
# The archive is validated with pg_restore --list before it gets its final name,
# so a truncated dump is never mistaken for a usable backup.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-../edu-crm-backups}"
DB_NAME="${DB_NAME:-edu_crm}"
DB_USER="${DB_USER:-crm}"
label="${1:-manual}"

if [[ ! "$label" =~ ^[a-z0-9-]+$ ]]; then
  echo "label must match [a-z0-9-]+" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/${DB_NAME}-$(date -u +%Y%m%dT%H%M%SZ)-${label}.dump"
partial="$file.partial"

docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$partial"
docker compose exec -T db pg_restore --list < "$partial" > /dev/null
mv "$partial" "$file"
echo "$file"
