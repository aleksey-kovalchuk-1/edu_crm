#!/usr/bin/env bash
# Archives uploaded documents (Docker volume documents_data, T-093) outside the repository, including the
# quarantine subdirectory. Run it together with db-backup.sh: the database holds the metadata, the volume
# holds the bytes. The archive is listed with tar before it gets its final name, so a truncated archive is
# never mistaken for a backup.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-../edu-crm-backups}"
label="${1:-manual}"

if [[ ! "$label" =~ ^[a-z0-9-]+$ ]]; then
  echo "label must match [a-z0-9-]+" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/documents-$(date -u +%Y%m%dT%H%M%SZ)-${label}.tar.gz"
partial="$file.partial"

docker compose exec -T api tar -C /data/documents -czf - . > "$partial"
count="$(tar -tzf "$partial" | grep -vc '/$' || true)"
mv "$partial" "$file"
echo "$file ($count files)"
