#!/usr/bin/env bash
# Streams the Compose database into an encrypted age file, never a plaintext dump.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."
source scripts/backup-age.sh

BACKUP_DIR="${BACKUP_DIR:-../edu-crm-backups}"
DB_NAME="${DB_NAME:-edu_crm}"
DB_USER="${DB_USER:-crm}"
label="${1:-manual}"

if [[ ! "$label" =~ ^[a-z0-9-]+$ ]]; then
  echo 'label must match [a-z0-9-]+' >&2; exit 2
fi
if [[ ! "$DB_NAME" =~ ^[a-z_][a-z0-9_]*$ ]]; then
  echo 'DB_NAME must be a simple database name' >&2; exit 2
fi
backup_age_recipient_preflight
backup_private_directory

file="$BACKUP_DIR/${DB_NAME}-$(date -u +%Y%m%dT%H%M%SZ)-${label}.dump.age"
if [[ -e "$file" ]]; then
  echo 'backup file already exists; choose a different label' >&2; exit 1
fi
partial="$(mktemp "$file.partial.XXXXXX")"
trap 'rm -f "$partial"' EXIT

docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc | age "${AGE_RECIPIENT_ARGS[@]}" > "$partial"
[[ -s "$partial" ]] || { echo 'encrypted backup is empty' >&2; exit 1; }
chmod 600 "$partial"
ln "$partial" "$file" || { echo 'backup file already exists' >&2; exit 1; }
echo "$file"
