#!/usr/bin/env bash
# Verify a new database dump and attachment archive with the recovery identity.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."
if [[ $# -ne 2 || "$1" != *.dump.age || "$2" != *.tar.gz.age ]]; then
  echo 'usage: verify-encrypted-pair.sh <database.dump.age> <attachments.tar.gz.age>' >&2; exit 2
fi
: "${BACKUP_AGE_IDENTITY_FILE:?set BACKUP_AGE_IDENTITY_FILE to the recovery key}"
[[ -f "$BACKUP_AGE_IDENTITY_FILE" && -r "$BACKUP_AGE_IDENTITY_FILE" ]] || {
  echo 'recovery identity is unreadable' >&2; exit 2;
}
command -v age >/dev/null || { echo 'age is required' >&2; exit 2; }
export COMPOSE_PROJECT_NAME=edu-crm
age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$1" | docker compose exec -T db pg_restore --list >/dev/null
# Consume the whole ciphertext as well as the dump header/TOC to verify age authentication.
age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$1" >/dev/null
scripts/attachments-verify.sh "$2" >/dev/null
echo 'Encrypted backup pair decrypted and parsed'
