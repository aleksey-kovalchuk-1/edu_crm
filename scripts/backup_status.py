"""Writes the backup status report (status.json) that Настройки → Резервное копирование shows.

Called by scripts/scheduled-backup.sh at the start (result=running) and at the end of every run. The report
holds only file names, sizes and dates — never paths, keys, age recipients or contents — and is replaced
atomically. Runs on the host's system Python, so it avoids newer syntax.
Spec: docs/superpowers/specs/2026-09-27-backup-settings-design.md.
"""
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
MAX_PAIRS = 60
FILE_RE = re.compile(r'^(edu_crm|attachments)-(\d{8}T\d{6}Z)-([a-z0-9-]+)\.(dump|tar\.gz)\.age$')
KIND = {'edu_crm': 'database', 'attachments': 'attachments'}


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def scan_pairs(backup_dir):
    pairs = {}
    for path in Path(backup_dir).iterdir():
        match = FILE_RE.match(path.name)
        if not match or not path.is_file():
            continue
        prefix, stamp, label = match.group(1), match.group(2), match.group(3)
        created = datetime.strptime(stamp, '%Y%m%dT%H%M%SZ').strftime('%Y-%m-%dT%H:%M:%SZ')
        pair = pairs.setdefault(label, {'label': label, 'database': None, 'attachments': None, '_sort': created})
        pair[KIND[prefix]] = {'file': path.name, 'size_bytes': path.stat().st_size, 'created_at': created}
        pair['_sort'] = max(pair['_sort'], created)
    ordered = sorted(pairs.values(), key=lambda p: p['_sort'], reverse=True)[:MAX_PAIRS]
    for pair in ordered:
        del pair['_sort']
    return ordered


def _previous(status_path):
    try:
        return json.loads(status_path.read_text())
    except (OSError, ValueError):
        return {}


def write_status(status_dir, backup_dir, trigger, label, started_at, result, verified, error,
                 retention_days, min_pairs, verification_configured, now=None):
    now = now or utc_now()
    status_path = Path(status_dir) / 'status.json'
    previous = _previous(status_path)
    report = {
        'schema': SCHEMA,
        'updated_at': now,
        'last_run': {
            'trigger': trigger, 'label': label, 'started_at': started_at,
            'finished_at': None if result == 'running' else now,
            'result': result, 'verified': verified, 'error': error,
        },
        'last_success_at': now if result == 'success' else previous.get('last_success_at'),
        'pairs': scan_pairs(backup_dir) if Path(backup_dir).is_dir() else [],
        'retention': {'days': retention_days, 'min_pairs': min_pairs,
                      'verification_configured': verification_configured},
    }
    handle, temporary = tempfile.mkstemp(dir=str(status_dir), prefix='.status-', suffix='.json')
    try:
        with os.fdopen(handle, 'w') as out:
            json.dump(report, out, ensure_ascii=False, indent=2)
        os.chmod(temporary, 0o644)  # no secrets inside; the API container reads it through a read-only mount
        os.replace(temporary, status_path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return report


def _bool(value):
    return {'true': True, 'false': False, '': None}[value]


def main():
    parser = argparse.ArgumentParser(description='Write the backup status report')
    parser.add_argument('--status-dir', required=True)
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--trigger', choices=('scheduled', 'manual'), required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--started-at', required=True)
    parser.add_argument('--result', choices=('running', 'success', 'failure'), required=True)
    parser.add_argument('--verified', choices=('true', 'false', ''), default='')
    parser.add_argument('--error', default='')
    parser.add_argument('--retention-days', type=int, required=True)
    parser.add_argument('--min-pairs', type=int, required=True)
    parser.add_argument('--verification-configured', choices=('true', 'false'), required=True)
    args = parser.parse_args()
    Path(args.status_dir).mkdir(parents=True, exist_ok=True)
    write_status(args.status_dir, args.backup_dir, args.trigger, args.label, args.started_at, args.result,
                 _bool(args.verified), args.error or None, args.retention_days, args.min_pairs,
                 _bool(args.verification_configured))


if __name__ == '__main__':
    main()
