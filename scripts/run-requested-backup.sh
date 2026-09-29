#!/usr/bin/env bash
# Runs a manual backup requested from Настройки → Резервное копирование. Started by the LaunchAgent
# deploy/launchd/tech.unicrm.backup-request.plist whenever the request folder changes.
#
# The API can only drop request.json into the request folder; this script takes the request atomically
# (so one request means one run), ignores its contents entirely (nothing from the container reaches a
# command line) and runs the same scripts/scheduled-backup.sh with a manual label. Manual copies are never
# deleted by the retention rule. Spec: docs/design/specs/2026-09-27-backup-settings-design.md.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

request_dir="${BACKUP_REQUEST_DIR:-$PWD/deploy/local/backup-requests}"
runner="${BACKUP_RUNNER:-scripts/scheduled-backup.sh}"
request="$request_dir/request.json"
claim="$request_dir/processing.json"
STALE_MINUTES=360  # a claim older than this belongs to a run that crashed

[[ -e "$request" || -L "$request" ]] || exit 0
# The request folder is writable by the container: never follow or act on a planted link.
if [[ -L "$request" || ! -f "$request" ]]; then
  echo 'Ignoring a request that is not a regular file' >&2
  exit 0
fi
if [[ -L "$claim" ]]; then
  rm -f "$claim"  # a link is never a real claim (removes the link itself, not its target)
fi
if [[ -e "$claim" ]]; then
  if [[ -n "$(find "$claim" -mmin +"$STALE_MINUTES" -print -quit)" ]]; then
    echo 'Clearing a stale manual-backup claim' >&2
    rm -f "$claim"
  else
    echo 'A manual backup is already running; the new request waits' >&2
    exit 0
  fi
fi
# rename(2) replaces a link at the destination instead of following it (unlike mv into a directory link);
# atomic within one folder, so a second trigger finds nothing to take.
python3 -c 'import os, sys; os.rename(sys.argv[1], sys.argv[2])' "$request" "$claim"
trap 'rm -f "$claim"' EXIT

label="manual-$(date -u +%Y%m%d-%H%M%S)"
echo "Running requested manual backup $label"
BACKUP_TRIGGER=manual BACKUP_LABEL="$label" "$runner"
