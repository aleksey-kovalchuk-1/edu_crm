"""Measures derived from recorded interaction status changes."""

from datetime import date, datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from .workflows import STAGE_GROUPS, stage_group


def first_implementation_at(changes: Iterable[tuple[int | None, int, datetime]]) -> datetime | None:
    """First recorded move from before training into training, never an inferred start date."""
    dates = [
        changed_at for previous, current, changed_at in changes
        if previous is not None and stage_group(previous) < 3 and stage_group(current) == 3
    ]
    return min(dates) if dates else None


def monthly_implementations(
    events: Iterable[datetime], period_from: date, period_to: date, time_zone: ZoneInfo,
) -> list[dict[str, str | int]]:
    """Count dated implementations by the viewer's calendar month, retaining empty months."""
    counts: dict[str, int] = {}
    for event in events:
        local_day = event.astimezone(time_zone).date()
        if period_from <= local_day <= period_to:
            key = local_day.strftime('%Y-%m')
            counts[key] = counts.get(key, 0) + 1
    result = []
    year, month = period_from.year, period_from.month
    while (year, month) <= (period_to.year, period_to.month):
        key = f'{year:04d}-{month:02d}'
        result.append({'month': key, 'count': counts.get(key, 0)})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def funnel_counts(reached: Iterable[tuple[int, int]]) -> list[dict[str, str | int]]:
    """A university contributes once to its furthest stage and all earlier stages."""
    furthest: dict[int, int] = {}
    for university_id, group in reached:
        furthest[university_id] = max(group, furthest.get(university_id, -1))
    return [
        {'name': name, 'count': sum(group >= index for group in furthest.values())}
        for index, name in enumerate(STAGE_GROUPS)
    ]


def top_universities(implemented: Iterable[tuple[int, str, int]]) -> list[dict[str, str | int]]:
    """Rank universities only by programs with a recorded implementation date."""
    totals: dict[int, dict[str, str | int]] = {}
    for university_id, name, students in implemented:
        row = totals.setdefault(university_id, {'id': university_id, 'name': name, 'programs': 0, 'students': 0})
        row['programs'] += 1
        row['students'] += students
    return sorted(totals.values(), key=lambda row: (-row['programs'], -row['students'], row['name']))[:5]
