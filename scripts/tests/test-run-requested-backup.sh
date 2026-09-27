#!/usr/bin/env bash
# Synthetic check of the manual-backup request agent: one run per request flag, manual label, safe no-ops.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -m 700 "$tmp/requests"
cat > "$tmp/fake-runner" <<'RUNNER'
#!/usr/bin/env bash
printf '%s %s\n' "$BACKUP_TRIGGER" "$BACKUP_LABEL" >> "$FAKE_RUN_LOG"
test -f "$BACKUP_REQUEST_DIR/processing.json"   # the request stays claimed while the backup runs
exit "${FAKE_RUN_EXIT:-0}"
RUNNER
chmod +x "$tmp/fake-runner"
export BACKUP_REQUEST_DIR="$tmp/requests" BACKUP_RUNNER="$tmp/fake-runner" FAKE_RUN_LOG="$tmp/runs.log"
: > "$FAKE_RUN_LOG"

"$root/scripts/run-requested-backup.sh"                      # no request: nothing happens
test ! -s "$FAKE_RUN_LOG"

printf '{"requested_at": "2026-09-27T12:00:00Z", "requested_by_user_id": 1}' > "$tmp/requests/request.json"
"$root/scripts/run-requested-backup.sh"
test "$(wc -l < "$FAKE_RUN_LOG" | tr -d ' ')" = 1
grep -Eq '^manual manual-[0-9]{8}-[0-9]{6}$' "$FAKE_RUN_LOG"
test ! -e "$tmp/requests/request.json" && test ! -e "$tmp/requests/processing.json"
"$root/scripts/run-requested-backup.sh"                      # re-triggered by its own changes: no second run
test "$(wc -l < "$FAKE_RUN_LOG" | tr -d ' ')" = 1

printf '{}' > "$tmp/requests/request.json"
printf '{}' > "$tmp/requests/processing.json"                # a run is in progress: leave the new request waiting
"$root/scripts/run-requested-backup.sh"
test "$(wc -l < "$FAKE_RUN_LOG" | tr -d ' ')" = 1 && test -e "$tmp/requests/request.json"

touch -t 202601010000 "$tmp/requests/processing.json"         # crashed run long ago: stale claim is cleared
"$root/scripts/run-requested-backup.sh"
test "$(wc -l < "$FAKE_RUN_LOG" | tr -d ' ')" = 2 && test ! -e "$tmp/requests/processing.json"

printf '{}' > "$tmp/requests/request.json"                   # a failed backup still releases the claim
if FAKE_RUN_EXIT=3 "$root/scripts/run-requested-backup.sh"; then echo 'failure was hidden' >&2; exit 1; fi
test ! -e "$tmp/requests/processing.json" && test ! -e "$tmp/requests/request.json"
echo 'Requested backup synthetic checks passed.'
