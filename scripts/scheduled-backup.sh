#!/usr/bin/env bash
# Daily encrypted database + attachment backup for the production LaunchAgent.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."
export PATH="${PATH:-/usr/bin:/bin}:/opt/homebrew/bin:/usr/local/bin"

# Scheduled (LaunchAgent at 03:30) or manual (scripts/run-requested-backup.sh sets both variables).
trigger="${BACKUP_TRIGGER:-scheduled}"
label="${BACKUP_LABEL:-daily-$(date -u +%Y%m%d)}"
[[ "$trigger" == scheduled || "$trigger" == manual ]] || { echo 'unknown backup trigger' >&2; exit 2; }
[[ "$label" =~ ^(daily|manual)-[a-z0-9-]+$ ]] || { echo 'unsafe backup label' >&2; exit 2; }

# Status report for Настройки → Резервное копирование (names, sizes, dates only; see scripts/backup_status.py).
status_dir="${BACKUP_STATUS_DIR:-$PWD/deploy/local/backup-status}"
# Written before any check, so even a run that fails on its configuration reports the failure; the
# backup folder and retention come from the configuration and are filled in once it has been read.
BACKUP_DIR="${BACKUP_DIR:-}"
retention_days=30
min_pairs=7
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
stage=preflight_failed
verified=''
verification_configured=false
write_status() {
  # A report that cannot be written must never fail or hide the backup itself.
  python3 scripts/backup_status.py --status-dir "$status_dir" --backup-dir "$BACKUP_DIR" --trigger "$trigger" \
    --label "$label" --started-at "$started_at" --result "$1" --verified "$verified" --error "${2:-}" \
    --retention-days "$retention_days" --min-pairs "$min_pairs" \
    --verification-configured "$verification_configured" >/dev/null 2>&1 \
    || echo 'backup status report not written' >&2
}
finish() {
  local code=$?
  if (( code == 0 )); then write_status success; else write_status failure "$stage"; fi
  exit "$code"
}
write_status running
trap finish EXIT

config="${BACKUP_CONFIG_FILE:-deploy/local/public-deploy.env}"
[[ -f "$config" && -r "$config" ]] || { echo 'backup config missing' >&2; exit 2; }
mode="$(stat -f %Lp "$config" 2>/dev/null || stat -c %a "$config")"
if (( (8#$mode & 077) != 0 )); then
  echo 'backup config must be private' >&2; exit 2
fi
source "$config"
if [[ -n "${BACKUP_STATUS_DIR:-}" && "$BACKUP_STATUS_DIR" != "$status_dir" ]]; then
  status_dir="$BACKUP_STATUS_DIR"  # the configuration names its own report folder
  write_status running
fi
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
[[ -n "${BACKUP_AGE_IDENTITY_FILE:-}" ]] && verification_configured=true
export BACKUP_DIR BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
export BACKUP_AGE_RECIPIENTS_FILE="${BACKUP_AGE_RECIPIENTS_FILE:-}"
export BACKUP_AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:-}"
export COMPOSE_PROJECT_NAME=edu-crm

source scripts/backup-age.sh
backup_age_recipient_preflight
backup_private_directory

echo 'Creating encrypted database backup'
stage=database_backup_failed
dump="$(scripts/db-backup.sh "$label")"
echo 'Creating encrypted attachment backup'
stage=attachments_backup_failed
archive="$(scripts/attachments-backup.sh "$label")"
if [[ -n "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  stage=verification_failed
  verified=false
  scripts/verify-encrypted-pair.sh "$dump" "$archive"
  verified=true
  stage=retention_failed
  # Removes only old *daily* pairs; manual copies are never deleted automatically.
  python3 scripts/prune-scheduled-backups.py "$BACKUP_DIR" \
    --retention-days "$retention_days" --min-pairs "$min_pairs"
else
  echo 'Retention skipped: no recovery identity configured' >&2
fi
echo 'Backup pair complete'
