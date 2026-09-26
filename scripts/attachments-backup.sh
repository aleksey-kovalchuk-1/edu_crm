#!/usr/bin/env bash
# Streams attachment bytes directly into age encryption outside the repository.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."
source scripts/backup-age.sh

BACKUP_DIR="${BACKUP_DIR:-../edu-crm-backups}"
label="${1:-manual}"

if [[ ! "$label" =~ ^[a-z0-9-]+$ ]]; then
  echo "label must match [a-z0-9-]+" >&2
  exit 2
fi
backup_age_recipient_preflight
backup_private_directory

file="$BACKUP_DIR/attachments-$(date -u +%Y%m%dT%H%M%SZ)-${label}.tar.gz.age"
if [[ -e "$file" ]]; then
  echo 'backup file already exists; choose a different label' >&2; exit 1
fi
partial="$(mktemp "$file.partial.XXXXXX")"
trap 'rm -f "$partial"' EXIT

docker compose exec -T api tar -C /data/attachments -czf - . | age "${AGE_RECIPIENT_ARGS[@]}" > "$partial"
[[ -s "$partial" ]] || { echo 'encrypted backup is empty' >&2; exit 1; }
chmod 600 "$partial"
ln "$partial" "$file" || { echo 'backup file already exists' >&2; exit 1; }
echo "$file"
