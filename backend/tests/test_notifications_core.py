from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db_migrate import alembic_config
from app.models import Notification, NotificationPreference, Task, University, UniversityManager, User, utcnow
from app.notifications import EVENT_TYPES, GROUPS, FOREVER, is_enabled, notify
from helpers import database


def test_migration_round_trip(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0027')
    command.downgrade(config, '0026')
    command.upgrade(config, '0027')


def test_catalog_has_twenty_events_in_four_groups_with_owner_defaults():
    assert len(EVENT_TYPES) == 20
    assert [g for g, _ in GROUPS] == ['universities', 'launches', 'tasks', 'contracts']
    on = {key for key, e in EVENT_TYPES.items() if e.default}
    assert on == {
        'university_assigned', 'university_unassigned', 'task_assigned', 'task_unassigned', 'task_deadline_changed',
        'task_due_today', 'task_overdue', 'task_commented', 'task_submitted_for_approval', 'task_review_decided',
        'task_closed',
    }


def _setup(db, *, roles=('crm-user',)):
    university = University(name='Вуз уведомлений', city='Москва', contact='')
    db.add(university)
    db.flush()
    anna = User(keycloak_sub='kc-anna', email='anna@x.test', full_name='Анна Петрова', roles=list(roles))
    boss = User(keycloak_sub='kc-boss', email='boss@x.test', full_name='Руководитель', roles=['crm-supervisor'])
    db.add_all([anna, boss])
    db.flush()
    db.add(UniversityManager(university_id=university.id, user_id=anna.id))
    db.flush()
    return university, anna, boss


def _notify(db, user, university, **overrides):
    values = dict(user_id=user.id, event_type='university_assigned', title='Назначение', body='Вы ответственный',
                  link_type='university', link_id=university.id, university_id=university.id, actor_user_id=None)
    values.update(overrides)
    return notify(db, **values)


def _count(db, user):
    return db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id))


def test_notify_creates_for_a_visible_enabled_recipient(database_url):
    with database(database_url) as db:
        university, anna, _ = _setup(db)
        assert _notify(db, anna, university) is True
        db.flush()
        assert _count(db, anna) == 1


def test_notify_skips_the_actor_inactive_disabled_paused_and_invisible(database_url):
    with database(database_url) as db:
        university, anna, boss = _setup(db)
        assert _notify(db, anna, university, actor_user_id=anna.id) is False
        db.add(NotificationPreference(user_id=anna.id, event_type='university_assigned', enabled=False))
        db.flush()
        assert _notify(db, anna, university) is False
        other = University(name='Чужой вуз', city='Москва', contact='')
        db.add(other)
        db.flush()
        assert _notify(db, anna, other, event_type='university_unassigned', link_id=other.id, university_id=other.id) is False
        anna.notifications_paused_until = FOREVER
        assert _notify(db, anna, university, event_type='university_unassigned') is False
        anna.notifications_paused_until = utcnow() - timedelta(minutes=1)  # expired pause does not block
        assert _notify(db, anna, university, event_type='university_unassigned') is True
        boss.is_active = False
        assert _notify(db, boss, university, event_type='university_unassigned') is False


def test_disabled_default_event_needs_an_explicit_opt_in(database_url):
    with database(database_url) as db:
        university, anna, _ = _setup(db)
        assert is_enabled(db, anna.id, 'university_contacts_changed') is False
        assert _notify(db, anna, university, event_type='university_contacts_changed') is False
        db.add(NotificationPreference(user_id=anna.id, event_type='university_contacts_changed', enabled=True))
        db.flush()
        assert _notify(db, anna, university, event_type='university_contacts_changed') is True


def test_dedupe_key_and_same_action_duplicates_create_one_row(database_url):
    with database(database_url) as db:
        university, anna, _ = _setup(db)
        assert _notify(db, anna, university) is True
        assert _notify(db, anna, university) is False  # same type, recipient and entity in one transaction
        assert _notify(db, anna, university, event_type='task_due_today', dedupe_key='k1') is True
        db.commit()
    with database(database_url) as db:
        anna = db.scalar(select(User).where(User.keycloak_sub == 'kc-anna'))
        university = db.scalar(select(University).where(University.name == 'Вуз уведомлений'))
        assert _notify(db, anna, university, event_type='task_due_today', dedupe_key='k1') is False
        db.commit()
        assert _count(db, anna) == 2


def test_database_rejects_a_duplicate_dedupe_key(database_url):
    with database(database_url) as db:
        university, anna, _ = _setup(db)
        for _ in range(2):
            db.add(Notification(user_id=anna.id, event_type='task_overdue', title='t', body='b', link_type='task',
                                link_id=1, dedupe_key='same'))
        with pytest.raises(IntegrityError):
            db.flush()


def test_task_visibility_is_checked_in_the_database(database_url):
    with database(database_url) as db:
        university, anna, boss = _setup(db)
        hidden = Task(title='Чужая', creator_id=boss.id)
        mine = Task(title='По вузу', creator_id=boss.id, university_id=university.id)
        db.add_all([hidden, mine])
        db.flush()
        assert _notify(db, anna, university, event_type='task_assigned', link_type='task', link_id=hidden.id, university_id=None) is False
        assert _notify(db, anna, university, event_type='task_assigned', link_type='task', link_id=mine.id) is True
