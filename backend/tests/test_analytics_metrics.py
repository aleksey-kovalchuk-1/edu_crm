from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.analytics_metrics import first_implementation_at, funnel_counts, monthly_implementations, top_universities


def test_implementation_requires_a_recorded_transition_into_training():
    initial = datetime(2026, 1, 1, tzinfo=timezone.utc)
    implemented = datetime(2026, 2, 2, tzinfo=timezone.utc)
    later = datetime(2026, 3, 3, tzinfo=timezone.utc)

    assert first_implementation_at([
        (None, 8, initial),  # Imported directly into training is not proof of implementation.
        (7, 8, implemented),  # Implementation -> training.
        (8, 9, later),  # Moving within training is not another implementation.
        (7, 8, later),  # Re-entry does not count twice.
    ]) == implemented


def test_implementation_is_unknown_without_a_transition_into_training():
    now = datetime(2026, 2, 2, tzinfo=timezone.utc)
    assert first_implementation_at([(None, 8, now), (8, 9, now)]) is None


def test_monthly_implementations_uses_profile_timezone_and_fills_empty_months():
    tokyo = ZoneInfo('Asia/Tokyo')
    events = [
        datetime(2025, 12, 31, 16, 0, tzinfo=timezone.utc),  # 1 Jan in Tokyo
        datetime(2026, 1, 31, 15, 30, tzinfo=timezone.utc),  # 1 Feb in Tokyo
        datetime(2026, 3, 31, 14, 59, tzinfo=timezone.utc),  # 31 Mar in Tokyo
        datetime(2026, 3, 31, 15, 0, tzinfo=timezone.utc),  # 1 Apr in Tokyo: excluded
    ]

    assert monthly_implementations(events, date(2026, 1, 1), date(2026, 3, 31), tokyo) == [
        {'month': '2026-01', 'count': 1},
        {'month': '2026-02', 'count': 1},
        {'month': '2026-03', 'count': 1},
    ]


def test_monthly_implementations_keeps_zero_months_and_inclusive_boundaries():
    events = [datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc)]

    assert monthly_implementations(events, date(2026, 1, 1), date(2026, 3, 31), ZoneInfo('UTC')) == [
        {'month': '2026-01', 'count': 1},
        {'month': '2026-02', 'count': 0},
        {'month': '2026-03', 'count': 1},
    ]


def test_funnel_counts_unique_universities_and_all_earlier_stages():
    assert funnel_counts([(1, 2), (1, 1), (2, 1)]) == [
        {'name': 'Первый контакт', 'count': 2},
        {'name': 'Документы', 'count': 2},
        {'name': 'Внедрение', 'count': 1},
        {'name': 'Обучение', 'count': 0},
        {'name': 'Сопровождение', 'count': 0},
    ]


def test_top_five_sorts_by_implemented_programs_then_students():
    rows = [
        (1, 'Вуз А', 10), (1, 'Вуз А', 15),
        (2, 'Вуз Б', 30), (2, 'Вуз Б', 5),
        (3, 'Вуз В', 40), (4, 'Вуз Г', 30), (5, 'Вуз Д', 20), (6, 'Вуз Е', 10),
    ]

    assert top_universities(rows) == [
        {'id': 2, 'name': 'Вуз Б', 'programs': 2, 'students': 35},
        {'id': 1, 'name': 'Вуз А', 'programs': 2, 'students': 25},
        {'id': 3, 'name': 'Вуз В', 'programs': 1, 'students': 40},
        {'id': 4, 'name': 'Вуз Г', 'programs': 1, 'students': 30},
        {'id': 5, 'name': 'Вуз Д', 'programs': 1, 'students': 20},
    ]
