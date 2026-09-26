#!/usr/bin/env bash
# Lists encrypted attachment archive members without writing plaintext to disk.
set -euo pipefail
set +x
umask 077

if [[ $# -ne 1 || "$1" != *.tar.gz.age || ! -f "$1" ]]; then
  echo 'usage: attachments-verify.sh <file.tar.gz.age>' >&2; exit 2
fi
command -v age >/dev/null || { echo 'age is required' >&2; exit 2; }
if [[ -z "${BACKUP_AGE_IDENTITY_FILE:-}" || ! -f "$BACKUP_AGE_IDENTITY_FILE" || ! -r "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  echo 'BACKUP_AGE_IDENTITY_FILE must point to a readable identity' >&2; exit 2
fi
age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$1" | tar -tzf -
