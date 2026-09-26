#!/usr/bin/env bash
# Isolated PostgreSQL and attachment round trip with synthetic contents only.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
real_docker="$(command -v docker)"
tmp="$(mktemp -d)"
container="edu-crm-backup-test-$$"
cleanup() {
  "$real_docker" rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT
mkdir -m 700 "$tmp/bin" "$tmp/backups" "$tmp/attachments" "$tmp/restored-attachments"
printf 'synthetic attachment only\n' > "$tmp/attachments/example.txt"
"$real_docker" run --rm -d --network none --name "$container" \
  -e POSTGRES_DB=synthetic_source -e POSTGRES_USER=crm -e POSTGRES_PASSWORD=synthetic-only \
  postgres:16-alpine >/dev/null
ready=0
for _ in $(seq 1 30); do
  if "$real_docker" exec "$container" pg_isready -U crm -d synthetic_source >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
"$real_docker" exec "$container" psql -U crm -d synthetic_source -v ON_ERROR_STOP=1 -c \
  "create table synthetic_rows (id integer primary key); insert into synthetic_rows values (1), (2)" >/dev/null
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == compose && "${2:-}" == exec && "${3:-}" == -T && "${4:-}" == db ]]; then
  shift 4
  exec "$REAL_DOCKER" exec -i "$TEST_CONTAINER" "$@"
fi
if [[ "${1:-}" == compose && "${2:-}" == exec && "${3:-}" == -T && "${4:-}" == api ]]; then
  shift 4
  if [[ "${1:-}" == tar ]]; then exec tar -C "$TEST_ATTACHMENTS" -czf - .; fi
fi
echo 'unexpected docker command' >&2
exit 9
EOF
chmod +x "$tmp/bin/docker"
export PATH="$tmp/bin:$PATH" REAL_DOCKER="$real_docker" TEST_CONTAINER="$container" TEST_ATTACHMENTS="$tmp/attachments"
age-keygen -o "$tmp/identity" >/dev/null 2>&1
recipient="$(age-keygen -y "$tmp/identity")"
BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" DB_NAME=synthetic_source \
  "$root/scripts/db-backup.sh" synthetic >/dev/null
dump="$(find "$tmp/backups" -name '*.dump.age' -print -quit)"
BACKUP_AGE_IDENTITY_FILE="$tmp/identity" "$root/scripts/db-restore.sh" "$dump" synthetic_restore >/dev/null
count="$("$real_docker" exec "$container" psql -U crm -d synthetic_restore -Atc 'select count(*) from synthetic_rows')"
test "$count" = 2
BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" "$root/scripts/attachments-backup.sh" synthetic >/dev/null
archive="$(find "$tmp/backups" -name '*.tar.gz.age' -print -quit)"
BACKUP_AGE_IDENTITY_FILE="$tmp/identity" "$root/scripts/attachments-verify.sh" "$archive" >/dev/null
age -d -i "$tmp/identity" "$archive" | tar -C "$tmp/restored-attachments" -xzf -
cmp "$tmp/attachments/example.txt" "$tmp/restored-attachments/example.txt"
test -z "$(find "$tmp/backups" -name '*.dump' -o -name '*.tar.gz' -o -name '*.partial*')"
echo 'Encrypted PostgreSQL and attachment round trip passed.'
