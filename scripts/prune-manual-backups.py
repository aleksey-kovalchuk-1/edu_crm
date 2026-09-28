#!/usr/bin/env python3
"""Pair-level cleanup of old *manual* backups (operator procedure, docs/operations/backup.md).

Manual copies (label manual-…) are never removed by the daily retention rule. This tool previews — and only
with --apply deletes — whole manual pairs (database + attachments with one label) whose files are both older
than --older-than-days. Pairs listed in the keep file (one "label reason" per line) are protected and never
deleted; incomplete pairs are only reported. Daily and release copies are out of scope here.
Runs on the host's system Python, so it avoids newer syntax.
"""
import argparse
import re
import sys
import time
from pathlib import Path

FILE_RE = re.compile(r'^(edu_crm|attachments)-\d{8}T\d{6}Z-(manual-[a-z0-9-]+)\.(dump|tar\.gz)\.age$')
KEEP_RE = re.compile(r'^(manual-[a-z0-9-]+)\s+(\S.*)$')
DAY = 86400


class Pair(object):
    def __init__(self, label):
        self.label = label
        self.database = None
        self.attachments = None

    @property
    def files(self):
        return [f for f in (self.database, self.attachments) if f is not None]

    @property
    def complete(self):
        return self.database is not None and self.attachments is not None


class Plan(object):
    def __init__(self, delete, protected, incomplete, kept_recent):
        self.delete = delete
        self.protected = protected
        self.incomplete = incomplete
        self.kept_recent = kept_recent


def read_keep_file(keep_file):
    """{label: reason}. Every protected label needs a reason, so a stray line cannot silently protect or not."""
    keep = {}
    if keep_file is None or not Path(keep_file).exists():
        return keep
    for number, line in enumerate(Path(keep_file).read_text(encoding='utf-8').splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = KEEP_RE.match(line)
        if not match:
            raise ValueError('keep file line %d: expected "<manual-label> <reason>"' % number)
        keep[match.group(1)] = match.group(2).strip()
    return keep


def plan_cleanup(backup_dir, keep_file=None, older_than_days=30, now=None):
    now = now or time.time()
    cutoff = now - older_than_days * DAY
    pairs = {}
    for path in Path(backup_dir).iterdir():
        match = FILE_RE.match(path.name)
        if not match or not path.is_file() or path.is_symlink():
            continue
        pair = pairs.setdefault(match.group(2), Pair(match.group(2)))
        if match.group(1) == 'edu_crm':
            pair.database = path
        else:
            pair.attachments = path
    keep = read_keep_file(keep_file)
    delete, protected, incomplete, recent = [], {}, [], []
    for label in sorted(pairs):
        pair = pairs[label]
        if label in keep:
            protected[label] = keep[label]
        elif not pair.complete:
            incomplete.append(pair)
        elif all(f.stat().st_mtime < cutoff for f in pair.files):
            delete.append(pair)
        else:
            recent.append(pair)
    return Plan(delete, protected, incomplete, recent)


def apply_plan(plan):
    removed = []
    for pair in plan.delete:
        for path in pair.files:
            path.unlink()
        removed.append(pair.label)
    return removed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup_dir')
    parser.add_argument('--keep-file', help='protected manual pairs: one "<label> <reason>" per line')
    parser.add_argument('--older-than-days', type=int, default=30)
    parser.add_argument('--apply', action='store_true', help='delete the listed pairs (default: preview only)')
    args = parser.parse_args(argv)
    if args.older_than_days < 1:
        parser.error('--older-than-days must be at least 1')
    plan = plan_cleanup(args.backup_dir, args.keep_file, args.older_than_days)
    for label, reason in sorted(plan.protected.items()):
        print('PROTECTED  %s  (%s)' % (label, reason))
    for pair in plan.incomplete:
        print('INCOMPLETE %s  (not deleted: %s)' % (pair.label, ', '.join(f.name for f in pair.files)))
    for pair in plan.delete:
        print('%s %s  %s' % ('DELETE    ' if args.apply else 'WOULD DELETE', pair.label,
                             ' + '.join(f.name for f in pair.files)))
    if args.apply:
        removed = apply_plan(plan)
        print('Deleted %d manual pair(s).' % len(removed))
    else:
        print('Preview only: %d manual pair(s) would be deleted. Re-run with --apply to delete them.' % len(plan.delete))
    return 0


if __name__ == '__main__':
    sys.exit(main())
