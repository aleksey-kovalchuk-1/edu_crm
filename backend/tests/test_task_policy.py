from datetime import date

import pytest
from sqlalchemy import select

from app.models import Task, TaskMember, University, UniversityManager, User
from app.task_policy import TaskAction, can, visible_tasks_query
from helpers import database


def make_user(db, *, full_name='Тест', roles=('crm-user',)):
    user = User(keycloak_sub=f'kc-{full_name}-{roles}', email='', full_name=full_name, roles=list(roles), is_active=True)
    db.add(user)
    db.flush()
    return user


def make_task(db, *, title='Задача', creator=None, university_id=None):
    task = Task(title=title, creator_id=creator.id if creator else None, university_id=university_id)
    db.add(task)
    db.flush()
    return task


@pytest.fixture
def db(database_url):
    with database(database_url) as session:
        yield session


def test_creator_can_view_own_task(db):
    creator = make_user(db, full_name='Автор')
    task = make_task(db, creator=creator)
    assert can(creator, TaskAction.VIEW, task)


def test_unrelated_user_cannot_view_task(db):
    creator = make_user(db, full_name='Автор')
    other = make_user(db, full_name='Посторонний')
    task = make_task(db, creator=creator)
    assert not can(other, TaskAction.VIEW, task)


def test_assignee_can_view_task_but_not_edit(db):
    creator = make_user(db, full_name='Автор')
    assignee = make_user(db, full_name='Исполнитель')
    task = make_task(db, creator=creator)
    db.add(TaskMember(task_id=task.id, user_id=assignee.id, role='assignee'))
    db.flush()
    assert can(assignee, TaskAction.VIEW, task)
    assert not can(assignee, TaskAction.EDIT, task)
    assert can(creator, TaskAction.EDIT, task)


def test_university_manager_sees_task_without_being_a_member(db):
    manager = make_user(db, full_name='Менеджер вуза')
    creator = make_user(db, full_name='Автор')
    university = University(name='Вуз А', city='Москва', contact='')
    db.add(university)
    db.flush()
    db.add(UniversityManager(university_id=university.id, user_id=manager.id))
    task = make_task(db, creator=creator, university_id=university.id)
    db.flush()
    assert can(manager, TaskAction.VIEW, task)


def test_manager_outside_university_scope_cannot_view(db):
    manager = make_user(db, full_name='Менеджер вуза')
    creator = make_user(db, full_name='Автор')
    other_university = University(name='Вуз Б', city='Казань', contact='')
    db.add(other_university)
    db.flush()
    task = make_task(db, creator=creator, university_id=other_university.id)
    db.flush()
    assert not can(manager, TaskAction.VIEW, task)


def test_supervisor_sees_and_manages_everything(db):
    supervisor = make_user(db, full_name='Руководитель', roles=('crm-supervisor',))
    creator = make_user(db, full_name='Автор')
    task = make_task(db, creator=creator)
    assert can(supervisor, TaskAction.VIEW, task)
    assert can(supervisor, TaskAction.REASSIGN, task)
    assert can(supervisor, TaskAction.ARCHIVE, task)


def test_only_supervisor_and_admin_manage_templates(db):
    user = make_user(db, full_name='Менеджер', roles=('crm-user',))
    supervisor = make_user(db, full_name='Руководитель', roles=('crm-supervisor',))
    assert not can(user, TaskAction.MANAGE_TEMPLATES)
    assert can(supervisor, TaskAction.MANAGE_TEMPLATES)


def test_visible_tasks_query_matches_can_view(db):
    creator = make_user(db, full_name='Автор')
    other = make_user(db, full_name='Посторонний')
    mine = make_task(db, title='Моя', creator=creator)
    make_task(db, title='Чужая', creator=other)
    db.commit()

    visible_ids = set(db.scalars(select(Task.id).where(visible_tasks_query(creator))))
    assert visible_ids == {mine.id}
