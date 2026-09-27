from datetime import date, datetime, timedelta, timezone

from sqlalchemy import update

from app.models import Contract, ITProduct, Task, TaskMember, University, UniversityManager, User
from app.notification_scheduler import run_once
from helpers import database
from notification_helpers import enable, notifications

UTC = timezone.utc


def _user(db, sub, tz='Europe/Moscow'):
    user = User(keycloak_sub=sub, email=f'{sub}@x.test', full_name=sub, roles=['crm-user'], timezone=tz)
    db.add(user)
    db.flush()
    return user


def _task(db, deadline, *members, status='new', archived=False):
    task = Task(title='Сдать отчёт', deadline=deadline, status=status,
                archived_at=datetime(2026, 1, 1, tzinfo=UTC) if archived else None)
    db.add(task)
    db.flush()
    for user in members:
        db.add(TaskMember(task_id=task.id, user_id=user.id, role='assignee'))
    db.flush()
    return task


def _due(database_url, event_type):
    return sorted((u, link_id) for u, t, _, link_id in notifications(database_url) if t == event_type)


def test_due_today_respects_each_users_time_zone_and_8am(app, database_url):
    with database(database_url) as db:
        moscow, vladivostok = _user(db, 'kc-msk'), _user(db, 'kc-vvo', 'Asia/Vladivostok')
        task = _task(db, date(2026, 10, 10), moscow, vladivostok)
        db.commit()
        ids = moscow.id, vladivostok.id, task.id
    run_once(app.state.session_factory, now=datetime(2026, 10, 10, 2, 0, tzinfo=UTC))  # Москва 05:00, Владивосток 12:00
    assert _due(database_url, 'task_due_today') == [(ids[1], ids[2])]
    run_once(app.state.session_factory, now=datetime(2026, 10, 10, 6, 0, tzinfo=UTC))  # Москва 09:00
    assert _due(database_url, 'task_due_today') == sorted([(ids[0], ids[2]), (ids[1], ids[2])])


def test_repeated_runs_add_nothing_and_a_moved_deadline_notifies_again(app, database_url):
    with database(database_url) as db:
        anna = _user(db, 'kc-anna')
        task = _task(db, date(2026, 10, 10), anna)
        db.commit()
        task_id = task.id
    now = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
    for _ in range(3):
        run_once(app.state.session_factory, now=now)
    assert len(_due(database_url, 'task_due_today')) == 1
    with database(database_url) as db:
        db.execute(update(Task).where(Task.id == task_id).values(deadline=date(2026, 10, 12)))
        db.commit()
    run_once(app.state.session_factory, now=datetime(2026, 10, 12, 9, 0, tzinfo=UTC))
    assert len(_due(database_url, 'task_due_today')) == 2


def test_overdue_once_and_closed_or_archived_tasks_are_skipped(app, database_url):
    with database(database_url) as db:
        anna = _user(db, 'kc-anna')
        late = _task(db, date(2026, 10, 1), anna)
        _task(db, date(2026, 10, 1), anna, status='completed')
        _task(db, date(2026, 10, 1), anna, status='cancelled')
        _task(db, date(2026, 10, 1), anna, archived=True)
        db.commit()
        expected = [(anna.id, late.id)]
    for day in (5, 6):
        run_once(app.state.session_factory, now=datetime(2026, 10, day, 9, 0, tzinfo=UTC))
    assert _due(database_url, 'task_overdue') == expected


def test_unknown_time_zone_falls_back_to_moscow(app, database_url):
    with database(database_url) as db:
        odd = _user(db, 'kc-odd', 'Mars/Olympus')
        _task(db, date(2026, 10, 10), odd)
        db.commit()
    run_once(app.state.session_factory, now=datetime(2026, 10, 10, 4, 0, tzinfo=UTC))  # Москва 07:00
    assert _due(database_url, 'task_due_today') == []
    run_once(app.state.session_factory, now=datetime(2026, 10, 10, 5, 30, tzinfo=UTC))  # Москва 08:30
    assert len(_due(database_url, 'task_due_today')) == 1


def test_license_expiry_warnings_at_30_and_7_days(app, database_url):
    with database(database_url) as db:
        anna = _user(db, 'kc-anna')
        university = University(name='Вуз лицензий', city='Москва', contact='')
        product = ITProduct(vendor='РТК ИТ', name='Среда')
        db.add_all([university, product])
        db.flush()
        db.add(UniversityManager(university_id=university.id, user_id=anna.id))
        contract = Contract(contract_number='Л-1', university_id=university.id, it_product_id=product.id,
                            signed_at=date(2025, 11, 9), valid_until=date(2026, 11, 9))
        db.add(contract)
        db.commit()
        anna_id, contract_id = anna.id, contract.id
    enable(database_url, anna_id, 'license_expires_30', 'license_expires_7')
    run_once(app.state.session_factory, now=datetime(2026, 10, 10, 9, 0, tzinfo=UTC))  # 30 days left
    run_once(app.state.session_factory, now=datetime(2026, 10, 11, 9, 0, tzinfo=UTC))  # 29: nothing new
    run_once(app.state.session_factory, now=datetime(2026, 11, 2, 9, 0, tzinfo=UTC))   # 7 days left
    assert _due(database_url, 'license_expires_30') == [(anna_id, contract_id)]
    assert _due(database_url, 'license_expires_7') == [(anna_id, contract_id)]


def test_paused_user_gets_nothing(app, database_url):
    with database(database_url) as db:
        anna = _user(db, 'kc-anna')
        anna.notifications_paused_until = datetime(2026, 10, 11, tzinfo=UTC)
        _task(db, date(2026, 10, 10), anna)
        db.commit()
    run_once(app.state.session_factory, now=datetime(2026, 10, 10, 9, 0, tzinfo=UTC))
    assert _due(database_url, 'task_due_today') == []
