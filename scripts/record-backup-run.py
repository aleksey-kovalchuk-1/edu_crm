#!/usr/bin/env python3
"""Publish the state of the latest backup run (running / success / failure with its stage).

Written by scripts/scheduled-backup.sh at the start and end of every run, next to the pair history
that scripts/record-backup-status.py maintains in status.json — that file is never touched here. The API
reads last-run.json through the same read-only mount, so Настройки → Резервное копирование can say that the
last run failed even though no new pair was recorded. No paths, keys or file names, only these fields.
Runs on the host's system Python, so it avoids newer syntax.
"""
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
RESULTS = ('running', 'success', 'failure')
TRIGGERS = ('scheduled', 'manual')
TOKEN = re.compile(r'^[a-z0-9_-]+$')


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def record_run(status_dir, trigger, label, started_at, result, error=None, now=None):
    if trigger not in TRIGGERS or result not in RESULTS:
        raise ValueError('invalid trigger or result')
    if not TOKEN.match(label) or (error is not None and not TOKEN.match(error)):
        raise ValueError('invalid label or error code')
    now = now or utc_now()
    status_dir = Path(status_dir)
    status_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    # Producers run with umask 077; the API's unprivileged user must still traverse this metadata-only folder.
    os.chmod(status_dir, 0o755)
    body = {'schema': SCHEMA, 'trigger': trigger, 'label': label, 'started_at': started_at,
            'finished_at': None if result == 'running' else now, 'result': result, 'error': error}
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(status_dir), prefix='.last-run-',
                                         delete=False) as temporary:
            name = temporary.name
            json.dump(body, temporary, ensure_ascii=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(name, 0o644)
        os.replace(name, str(status_dir / 'last-run.json'))
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('status_dir', type=Path)
    parser.add_argument('trigger', choices=TRIGGERS)
    parser.add_argument('label')
    parser.add_argument('started_at')
    parser.add_argument('result', choices=RESULTS)
    parser.add_argument('--error', default=None)
    args = parser.parse_args()
    record_run(args.status_dir, args.trigger, args.label, args.started_at, args.result, args.error)


if __name__ == '__main__':
    main()
