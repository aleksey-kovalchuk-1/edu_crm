#!/usr/bin/env bash
# Synthetic local round trips; never touches the real Compose database.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -m 700 "$tmp/bin" "$tmp/backups" "$tmp/attachments"
printf 'synthetic attachment\n' > "$tmp/attachments/member.txt"
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *'pg_dump '*)
    printf 'synthetic pg dump\n'
    if [[ "${FAIL_DUMP:-}" == 1 ]]; then exit 7; fi ;;
  *'pg_restore --list'*) cat >/dev/null ;;
  *'pg_restore -U '*) cat >/dev/null ;;
  *'psql -U '*) printf '%s' "${FAKE_DATABASE_EXISTS:-}" ;;
  *'createdb -U '*) : ;;
  *'tar -C /data/attachments'*)
    tar -C "$FAKE_ATTACHMENTS" -czf - .
    if [[ "${FAIL_TAR:-}" == 1 ]]; then exit 7; fi ;;
  *) echo "unexpected docker call" >&2; exit 9 ;;
esac
EOF
chmod +x "$tmp/bin/docker"
export PATH="$tmp/bin:$PATH" FAKE_DOCKER_LOG="$tmp/docker.log" FAKE_ATTACHMENTS="$tmp/attachments"
age-keygen -o "$tmp/identity" >/dev/null 2>&1
recipient="$(age-keygen -y "$tmp/identity")"
if BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT='' "$root/scripts/db-backup.sh" synthetic >/dev/null 2>&1; then
  echo 'db backup accepted a missing recipient' >&2; exit 1
fi
test ! -s "$tmp/docker.log"
mkdir -m 700 "$tmp/no-age-bin"
printf '#!/usr/bin/env bash\nexit 127\n' > "$tmp/no-age-bin/age"
chmod +x "$tmp/no-age-bin/age"
if PATH="$tmp/no-age-bin:$PATH" BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" \
    "$root/scripts/db-backup.sh" no-age >/dev/null 2>&1; then
  echo 'db backup accepted missing age' >&2; exit 1
fi
test ! -s "$tmp/docker.log"
BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" "$root/scripts/db-backup.sh" synthetic >/dev/null
dump="$(find "$tmp/backups" -name '*.dump.age' -print -quit)"
test -n "$dump"
test "$(age -d -i "$tmp/identity" "$dump")" = 'synthetic pg dump'
test "$(stat -f %Lp "$dump" 2>/dev/null || stat -c %a "$dump")" = 600
if BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" FAIL_DUMP=1 "$root/scripts/db-backup.sh" failed >/dev/null 2>&1; then
  echo 'db backup accepted failed pg_dump' >&2; exit 1
fi
test -z "$(find "$tmp/backups" -name '*failed*.age' -o -name '*.partial*')"
mkdir -m 700 "$tmp/fail-age-bin"
real_age="$(command -v age)"
cat > "$tmp/fail-age-bin/age" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *'-o /dev/null'* ]]; then exec "$FAKE_REAL_AGE" "$@"; fi
exit 9
EOF
chmod +x "$tmp/fail-age-bin/age"
if PATH="$tmp/fail-age-bin:$PATH" FAKE_REAL_AGE="$real_age" BACKUP_DIR="$tmp/backups" \
    BACKUP_AGE_RECIPIENT="$recipient" "$root/scripts/db-backup.sh" encrypt-failed >/dev/null 2>&1; then
  echo 'db backup accepted failed encryption' >&2; exit 1
fi
test -z "$(find "$tmp/backups" -name '*encrypt-failed*.age' -o -name '*.partial*')"

if BACKUP_AGE_IDENTITY_FILE="$tmp/identity" "$root/scripts/db-restore.sh" "$dump" synthetic_restore >/dev/null; then :; else
  echo 'synthetic db restore failed' >&2; exit 1
fi
test "$(rg -c 'createdb -U crm synthetic_restore' "$tmp/docker.log")" = 1
age-keygen -o "$tmp/wrong-identity" >/dev/null 2>&1
if BACKUP_AGE_IDENTITY_FILE="$tmp/wrong-identity" "$root/scripts/db-restore.sh" "$dump" wrong_restore >/dev/null 2>&1; then
  echo 'wrong identity accepted' >&2; exit 1
fi
! rg -q 'createdb -U crm wrong_restore' "$tmp/docker.log"
head -c 20 "$dump" > "$tmp/truncated.dump.age"
if BACKUP_AGE_IDENTITY_FILE="$tmp/identity" "$root/scripts/db-restore.sh" "$tmp/truncated.dump.age" broken_restore >/dev/null 2>&1; then
  echo 'truncated ciphertext accepted' >&2; exit 1
fi
! rg -q 'createdb -U crm broken_restore' "$tmp/docker.log"
if BACKUP_AGE_IDENTITY_FILE="$tmp/identity" FAKE_DATABASE_EXISTS=1 "$root/scripts/db-restore.sh" "$dump" existing_restore >/dev/null 2>&1; then
  echo 'existing database accepted' >&2; exit 1
fi
! rg -q 'createdb -U crm existing_restore' "$tmp/docker.log"

BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" "$root/scripts/attachments-backup.sh" synthetic >/dev/null
archive="$(find "$tmp/backups" -name '*.tar.gz.age' -print -quit)"
test -n "$archive"
if BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENT="$recipient" FAIL_TAR=1 \
    "$root/scripts/attachments-backup.sh" failed-attachments >/dev/null 2>&1; then
  echo 'attachment backup accepted failed tar' >&2; exit 1
fi
test -z "$(find "$tmp/backups" -name '*failed-attachments*.age' -o -name '*.partial*')"
BACKUP_AGE_IDENTITY_FILE="$tmp/identity" "$root/scripts/attachments-verify.sh" "$archive" >/dev/null
if BACKUP_AGE_IDENTITY_FILE="$tmp/wrong-identity" "$root/scripts/attachments-verify.sh" "$archive" >/dev/null 2>&1; then
  echo 'wrong attachment identity accepted' >&2; exit 1
fi
test "$(age -d -i "$tmp/identity" "$archive" | tar -tzf - | rg -c 'member.txt')" = 1

age-keygen -o "$tmp/new-identity" >/dev/null 2>&1
printf '%s\n%s\n' "$recipient" "$(age-keygen -y "$tmp/new-identity")" > "$tmp/recipients"
BACKUP_DIR="$tmp/backups" BACKUP_AGE_RECIPIENTS_FILE="$tmp/recipients" "$root/scripts/db-backup.sh" rotation >/dev/null
rotated="$(find "$tmp/backups" -name '*rotation.dump.age' -print -quit)"
test "$(age -d -i "$tmp/identity" "$rotated")" = 'synthetic pg dump'
test "$(age -d -i "$tmp/new-identity" "$rotated")" = 'synthetic pg dump'
test -z "$(find "$tmp/backups" -name '*.dump' -o -name '*.tar.gz' -o -name '*.partial*')"
echo 'Encrypted backup synthetic checks passed.'
