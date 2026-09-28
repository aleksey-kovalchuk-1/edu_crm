#!/usr/bin/env bash
# Synthetic end-to-end check: daily backup order and private checkout guard.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -m 700 "$tmp/bin" "$tmp/backups" "$tmp/attachments"
printf 'synthetic attachment\n' > "$tmp/attachments/item.txt"
age-keygen -o "$tmp/identity" >/dev/null 2>&1
recipient="$(age-keygen -y "$tmp/identity")"
printf 'BACKUP_DIR=%q\nBACKUP_AGE_RECIPIENT=%q\nBACKUP_AGE_IDENTITY_FILE=%q\nDEPLOY_CHECKOUT=%q\n' \
  "$tmp/backups" "$recipient" "$tmp/identity" "$root" > "$tmp/config.env"
chmod 600 "$tmp/config.env"

cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *'exec -T db pg_dump '*) printf 'synthetic database\n' ;;
  *'exec -T api tar -C /data/attachments -czf - .'*)
    if [[ "${FAIL_ATTACHMENT:-}" == 1 ]]; then exit 7; fi
    tar -C "$FAKE_ATTACHMENTS" -czf - . ;;
  *'exec -T db pg_restore --list'*) cat >/dev/null ;;
  *) echo "unexpected Docker command" >&2; exit 9 ;;
esac
EOF
chmod +x "$tmp/bin/docker"
export PATH="$tmp/bin:$PATH" FAKE_DOCKER_LOG="$tmp/docker.log"
export FAKE_ATTACHMENTS="$tmp/attachments" BACKUP_CONFIG_FILE="$tmp/config.env"
export BACKUP_STATUS_DIR="$tmp/status"
"$root/scripts/scheduled-backup.sh" >/dev/null
dump="$(find "$tmp/backups" -name '*.dump.age' -print -quit)"
archive="$(find "$tmp/backups" -name '*.tar.gz.age' -print -quit)"
test -n "$dump" && test -n "$archive"
test "$(age -d -i "$tmp/identity" "$dump")" = 'synthetic database'
test "$(age -d -i "$tmp/identity" "$archive" | tar -tzf - | rg -c 'item.txt')" = 1
python3 - "$tmp/status/status.json" <<'PY'
import json, sys
entry = json.load(open(sys.argv[1]))['backups'][0]
assert entry['source'].startswith('daily-') and entry['verified'] is True
PY
python3 - "$tmp/docker.log" <<'PY'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
assert len(lines) == 3 and 'pg_dump' in lines[0] and 'tar ' in lines[1] and 'pg_restore --list' in lines[2], lines
PY

printf 'BACKUP_DIR=%q\nBACKUP_AGE_RECIPIENT=%q\nDEPLOY_CHECKOUT=%q\n' \
  "$tmp/backups" "$recipient" "$tmp" > "$tmp/wrong.env"
chmod 600 "$tmp/wrong.env"
: > "$tmp/docker.log"
if BACKUP_CONFIG_FILE="$tmp/wrong.env" "$root/scripts/scheduled-backup.sh" >/dev/null 2>&1; then
  echo 'daily backup accepted another checkout' >&2; exit 1
fi
test ! -s "$tmp/docker.log"

# A syntactically valid but wrong age recipient must never trigger retention.
mkdir -m 700 "$tmp/wrong-recipient-backups"
age-keygen -o "$tmp/other-identity" >/dev/null 2>&1
other_recipient="$(age-keygen -y "$tmp/other-identity")"
old_dump="$tmp/wrong-recipient-backups/edu_crm-20260801T033000Z-daily-20260801.dump.age"
old_archive="$tmp/wrong-recipient-backups/attachments-20260801T033001Z-daily-20260801.tar.gz.age"
printf 'synthetic old backup' | age -r "$recipient" > "$old_dump"
tar -C "$tmp/attachments" -czf - . | age -r "$recipient" > "$old_archive"
printf 'BACKUP_DIR=%q\nBACKUP_AGE_RECIPIENT=%q\nBACKUP_AGE_IDENTITY_FILE=%q\nDEPLOY_CHECKOUT=%q\nBACKUP_RETENTION_DAYS=1\nBACKUP_MIN_PAIRS=1\n' \
  "$tmp/wrong-recipient-backups" "$other_recipient" "$tmp/identity" "$root" > "$tmp/wrong-recipient.env"
chmod 600 "$tmp/wrong-recipient.env"
if BACKUP_CONFIG_FILE="$tmp/wrong-recipient.env" "$root/scripts/scheduled-backup.sh" >/dev/null 2>&1; then
  echo 'daily backup accepted a recipient that cannot be recovered' >&2; exit 1
fi
test -f "$old_dump" && test -f "$old_archive"
# Latest-run report (last-run.json) next to the pair history: success, failure stage, early failure, manual.
python3 - "$tmp/status/last-run.json" <<'PY'
import json, sys
run = json.load(open(sys.argv[1]))
assert run['result'] != 'running', run  # every earlier run in this test finished and reported
PY
: > "$tmp/docker.log"
# Each extra run gets its own label: the backup scripts refuse to overwrite an existing file.
BACKUP_LABEL=daily-20260101 "$root/scripts/scheduled-backup.sh" >/dev/null
python3 - "$tmp/status/last-run.json" <<'PY'
import json, sys
run = json.load(open(sys.argv[1]))
assert run['result'] == 'success' and run['trigger'] == 'scheduled' and run['label'] == 'daily-20260101', run
assert run['error'] is None and run['finished_at'], run
PY
if FAIL_ATTACHMENT=1 BACKUP_LABEL=daily-20260102 "$root/scripts/scheduled-backup.sh" >/dev/null 2>&1; then
  echo 'failing attachment backup reported success' >&2; exit 1
fi
python3 - "$tmp/status/last-run.json" <<'PY'
import json, sys
run = json.load(open(sys.argv[1]))
assert run['result'] == 'failure' and run['error'] == 'attachments_backup_failed', run
PY
if BACKUP_CONFIG_FILE="$tmp/missing.env" BACKUP_TRIGGER=manual BACKUP_LABEL=manual-20260928-100000 \
    "$root/scripts/scheduled-backup.sh" >/dev/null 2>&1; then
  echo 'a run without config succeeded' >&2; exit 1
fi
python3 - "$tmp/status/last-run.json" <<'PY'
import json, sys
run = json.load(open(sys.argv[1]))
assert (run['result'], run['error'], run['trigger'], run['label']) == ('failure', 'preflight_failed', 'manual', 'manual-20260928-100000'), run
PY
BACKUP_TRIGGER=manual BACKUP_LABEL=manual-20260928-110000 "$root/scripts/scheduled-backup.sh" >/dev/null
python3 - "$tmp/status/status.json" "$tmp/status/last-run.json" <<'PY'
import json, sys
history, run = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
assert history['backups'][0]['source'] == 'manual-20260928-110000', history['backups'][0]
assert run['result'] == 'success' and run['trigger'] == 'manual', run
PY
if BACKUP_LABEL='../evil' "$root/scripts/scheduled-backup.sh" >/dev/null 2>&1; then
  echo 'an unsafe label was accepted' >&2; exit 1
fi

echo 'Scheduled backup synthetic checks passed.'
