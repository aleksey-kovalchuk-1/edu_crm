#!/usr/bin/env python3
"""Publish sanitized metadata for one complete encrypted backup pair.

The API receives only this JSON file, never the backup directory or recovery key.
"""
import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_HISTORY = 20


def file_id(path: Path) -> str:
    """Opaque reference used only by the host to discard rows after archive retention."""
    return hashlib.sha256(path.name.encode('utf-8')).hexdigest()[:24]


def record(status: Path, dump: Path, archive: Path, source: str, *, verified: bool) -> None:
    if not re.fullmatch(r'[a-z0-9-]+', source):
        raise ValueError('invalid backup label')
    if not dump.name.endswith('.dump.age') or not archive.name.endswith('.tar.gz.age'):
        raise ValueError('expected encrypted database and attachment files')
    database_bytes = dump.stat().st_size
    attachments_bytes = archive.stat().st_size
    if not database_bytes or not attachments_bytes:
        raise ValueError('backup pair contains an empty file')
    if dump.parent.resolve() != archive.parent.resolve():
        raise ValueError('backup files must share one directory')
    status.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    # Producers run with umask 077; the API's unprivileged user still needs to traverse this
    # metadata-only directory. The encrypted archives and recovery key are elsewhere.
    os.chmod(status.parent, 0o755)
    try:
        previous = json.loads(status.read_text(encoding='utf-8'))['backups']
    except FileNotFoundError:
        previous = []
    if not isinstance(previous, list):
        raise ValueError('invalid existing backup status')
    existing_ids = {file_id(path) for path in dump.parent.iterdir()
                    if path.is_file() and path.name.endswith('.age') and path.stat().st_size > 0}
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    entry = {'created_at': now, 'source': source, 'database_bytes': database_bytes,
             'attachments_bytes': attachments_bytes, 'verified': verified,
             'database_file_id': file_id(dump), 'attachments_file_id': file_id(archive)}
    previous = [item for item in previous if isinstance(item, dict)
                and item.get('database_file_id') in existing_ids
                and item.get('attachments_file_id') in existing_ids
                and (item['database_file_id'], item['attachments_file_id'])
                != (entry['database_file_id'], entry['attachments_file_id'])]
    body = {'generated_at': now, 'backups': [entry, *previous][:MAX_HISTORY]}
    content = json.dumps(body, ensure_ascii=False, separators=(',', ':')) + '\n'
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=status.parent, prefix='.status-',
                                         delete=False) as temporary:
            name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(name, 0o644)  # Only sanitized metadata; the unprivileged API container must read it.
        os.replace(name, status)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('status', type=Path)
    parser.add_argument('database', type=Path)
    parser.add_argument('attachments', type=Path)
    parser.add_argument('source')
    parser.add_argument('--verified', action='store_true')
    args = parser.parse_args()
    record(args.status, args.database, args.attachments, args.source, verified=args.verified)


if __name__ == '__main__':
    main()
