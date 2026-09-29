from sqlalchemy import select

from app.models import AuditEvent, Task, University
from app.sync_partner_universities import DEMO_NAMES, PARTNERS, sync_partner_universities
from helpers import database


def test_partner_roster_archives_demo_without_losing_linked_task(database_url):
    with database(database_url) as db:
        demo = University(name=DEMO_NAMES[0], city='Санкт-Петербург')
        db.add(demo)
        db.flush()
        task = Task(title='Историческая задача', university_id=demo.id)
        db.add(task)
        db.commit()
        old_id, task_id = demo.id, task.id

    with database(database_url) as db:
        preview = sync_partner_universities(db, apply=False)
        assert preview == {'created': 10, 'reactivated': 0, 'archived_demo': 1, 'shared_with_managers': 10, 'emails_filled': 0}
        assert db.scalar(select(University.is_active).where(University.id == old_id)) is True
        result = sync_partner_universities(db, apply=True)
        db.commit()
        assert result == preview

    with database(database_url) as db:
        active = db.scalars(select(University).where(University.is_active.is_(True))).all()
        assert {university.name for university in active} == {item.name for item in PARTNERS}
        assert len(active) == 10
        assert all(university.team_visible_to_managers for university in active)
        assert db.get(University, old_id).is_active is False
        assert db.get(University, old_id).team_visible_to_managers is False
        assert db.get(Task, task_id).university_id == old_id
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == 'university.roster_sync'))
        assert sync_partner_universities(db, apply=True) == {
            'created': 0, 'reactivated': 0, 'archived_demo': 0, 'shared_with_managers': 0, 'emails_filled': 0,
        }


def test_partner_roster_refuses_unexpected_active_university(database_url):
    with database(database_url) as db:
        db.add(University(name='Неизвестный действующий вуз', city='Москва'))
        db.commit()
    with database(database_url) as db:
        try:
            sync_partner_universities(db, apply=True)
        except ValueError as error:
            assert 'unexpected active' in str(error)
        else:
            raise AssertionError('Unexpected active university was silently archived or retained')
        db.rollback()
    with database(database_url) as db:
        assert db.scalar(select(University.is_active).where(University.name == 'Неизвестный действующий вуз')) is True
        assert db.scalar(select(University.id).where(University.name == PARTNERS[0].name)) is None
