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

# Latest-run report (last-run.json) beside the pair history (status.json), written before any check so a run
# that fails on its configuration still says so. A report that cannot be written never fails the backup.
run_status_dir="${BACKUP_STATUS_DIR:-deploy/local/backup-status}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
stage=preflight_failed
record_run() {
  python3 scripts/record-backup-run.py "$run_status_dir" "$trigger" "$label" "$started_at" "$@" >/dev/null 2>&1 \
    || echo 'backup run report not written' >&2
}
finish_run() {
  local code=$?
  if (( code == 0 )); then record_run success; else record_run failure --error "$stage"; fi
  exit "$code"
}
record_run running
trap finish_run EXIT

config="${BACKUP_CONFIG_FILE:-deploy/local/public-deploy.env}"
[[ -f "$config" && -r "$config" ]] || { echo 'backup config missing' >&2; exit 2; }
mode="$(stat -f %Lp "$config" 2>/dev/null || stat -c %a "$config")"
if (( (8#$mode & 077) != 0 )); then
  echo 'backup config must be private' >&2; exit 2
fi
source "$config"
if [[ -n "${BACKUP_STATUS_DIR:-}" && "$BACKUP_STATUS_DIR" != "$run_status_dir" ]]; then
  run_status_dir="$BACKUP_STATUS_DIR"  # the configuration names its own report folder
  record_run running
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
verified=()
if [[ -n "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  stage=verification_failed
  scripts/verify-encrypted-pair.sh "$dump" "$archive"
  verified=(--verified)
fi
if [[ -n "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  stage=retention_failed
  # Removes only old *daily* pairs; manual copies are never deleted automatically.
  python3 scripts/prune-scheduled-backups.py "$BACKUP_DIR" \
    --retention-days "$retention_days" --min-pairs "$min_pairs"
else
  echo 'Retention skipped: no recovery identity configured' >&2
fi
stage=status_record_failed
python3 scripts/record-backup-status.py "${BACKUP_STATUS_DIR:-deploy/local/backup-status}/status.json" \
  "$dump" "$archive" "$label" "${verified[@]}"
echo 'Daily backup pair complete'
