#!/usr/bin/env python3
"""Expire only complete, old scheduled backup days; never touch manual releases."""

import argparse
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


DAILY_FILE = re.compile(
    r'^(?P<kind>edu_crm|attachments)-(?P<stamp>\d{8})T\d{6}Z-daily-'
    r'(?P<day>\d{8})(?P<extension>\.dump\.age|\.tar\.gz\.age)$'
)


def prune_backup_pairs(directory: Path, *, retention_days: int, min_pairs: int,
                       now: datetime | None = None) -> int:
    if retention_days < 1 or min_pairs < 1:
        raise ValueError('retention_days and min_pairs must be positive')
    now = now or datetime.now(timezone.utc)
    cutoff = now.date() - timedelta(days=retention_days)
    groups: dict[date, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    for path in directory.iterdir():
        match = DAILY_FILE.fullmatch(path.name)
        if match is None or not path.is_file():
            continue
        kind = match['kind']
        expected_extension = '.dump.age' if kind == 'edu_crm' else '.tar.gz.age'
        if match['extension'] != expected_extension or match['stamp'] != match['day']:
            continue
        try:
            day = datetime.strptime(match['day'], '%Y%m%d').date()
        except ValueError:
            continue
        groups[day][kind].append(path)

    complete_days = sorted((day for day, kinds in groups.items()
                            if kinds['edu_crm'] and kinds['attachments']), reverse=True)
    protected = set(complete_days[:min_pairs])
    removed = 0
    for day in complete_days:
        if day >= cutoff or day in protected:
            continue
        for paths in groups[day].values():
            for path in paths:
                path.unlink()
        removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--retention-days', type=int, default=30)
    parser.add_argument('--min-pairs', type=int, default=7)
    args = parser.parse_args()
    removed = prune_backup_pairs(args.directory, retention_days=args.retention_days,
                                 min_pairs=args.min_pairs)
    print(f'Expired scheduled backup days: {removed}')


if __name__ == '__main__':
    main()
