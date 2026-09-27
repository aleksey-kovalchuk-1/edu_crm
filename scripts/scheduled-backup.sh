#!/usr/bin/env bash
# Daily encrypted database + attachment backup for the production LaunchAgent.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."
export PATH="${PATH:-/usr/bin:/bin}:/opt/homebrew/bin:/usr/local/bin"

config="${BACKUP_CONFIG_FILE:-deploy/local/public-deploy.env}"
[[ -f "$config" && -r "$config" ]] || { echo 'backup config missing' >&2; exit 2; }
mode="$(stat -f %Lp "$config" 2>/dev/null || stat -c %a "$config")"
if (( (8#$mode & 077) != 0 )); then
  echo 'backup config must be private' >&2; exit 2
fi
source "$config"
: "${BACKUP_DIR:?BACKUP_DIR is required}"
: "${DEPLOY_CHECKOUT:?DEPLOY_CHECKOUT is required}"
if [[ "$(cd "$DEPLOY_CHECKOUT" && pwd -P)" != "$(pwd -P)" ]]; then
  echo 'backup config belongs to a different checkout' >&2; exit 2
fi
retention_days="${BACKUP_RETENTION_DAYS:-30}"
min_pairs="${BACKUP_MIN_PAIRS:-7}"
[[ "$retention_days" =~ ^[1-9][0-9]*$ && "$min_pairs" =~ ^[1-9][0-9]*$ ]] || {
  echo 'backup retention and minimum pair counts must be positive' >&2; exit 2;
}
export BACKUP_DIR BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
export BACKUP_AGE_RECIPIENTS_FILE="${BACKUP_AGE_RECIPIENTS_FILE:-}"
export BACKUP_AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:-}"
export COMPOSE_PROJECT_NAME=edu-crm
source scripts/backup-age.sh
backup_age_recipient_preflight
backup_private_directory

label="daily-$(date -u +%Y%m%d)"
echo 'Creating daily encrypted database backup'
dump="$(scripts/db-backup.sh "$label")"
echo 'Creating daily encrypted attachment backup'
archive="$(scripts/attachments-backup.sh "$label")"
if [[ -n "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  scripts/verify-encrypted-pair.sh "$dump" "$archive"
  python3 scripts/prune-scheduled-backups.py "$BACKUP_DIR" \
    --retention-days "$retention_days" --min-pairs "$min_pairs"
else
  echo 'Retention skipped: no recovery identity configured' >&2
fi
echo 'Daily backup pair complete'
