from sqlalchemy import select

from app.models import AuditEvent, TaskEvent
from helpers import database, login


def create_task(client, **overrides):
    body = {'title': 'Задача', **overrides}
    response = client.post('/api/v1/tasks', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, task_id, to_status, comment='', version=None):
    return client.post(f'/api/v1/tasks/{task_id}/status', json={'to_status': to_status, 'comment': comment, 'version': version})


def test_assignee_starts_and_completes_without_approval(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-user',))
    task = create_task(client, assignee_ids=[me['user']['id']])

    started = set_status(client, task['id'], 'in_progress', version=task['version'])
    assert started.status_code == 200, started.text
    assert started.json()['status'] == 'in_progress'

    completed = set_status(client, task['id'], 'completed', version=started.json()['version'])
    assert completed.status_code == 200, completed.text
    assert completed.json()['status'] == 'completed'


def test_approval_required_task_needs_review_before_completion(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-user',))
    task = create_task(client, assignee_ids=[me['user']['id']], approval_required=True)
    task = set_status(client, task['id'], 'in_progress', version=task['version']).json()

    direct_complete = set_status(client, task['id'], 'completed', version=task['version'])
    assert direct_complete.status_code == 422
    assert direct_complete.json()['details'][0]['field'] == 'to_status'

    submitted = set_status(client, task['id'], 'awaiting_review', version=task['version'])
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()['status'] == 'awaiting_review'


def test_only_manager_may_accept_or_return_review(client, keycloak, database_url):
    assignee = login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='a@demo.local')
    assignee_id = assignee['user']['id']
    client.cookies.clear()

    login(client, keycloak, subject='kc-super', roles=('crm-supervisor',))
    task = create_task(client, assignee_ids=[assignee_id], approval_required=True)
    task = set_status(client, task['id'], 'in_progress', version=task['version']).json()
    task = set_status(client, task['id'], 'awaiting_review', version=task['version']).json()

    client.cookies.clear()
    login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='a@demo.local')
    denied = set_status(client, task['id'], 'completed', version=task['version'])
    assert denied.status_code == 403

    client.cookies.clear()
    login(client, keycloak, subject='kc-super', roles=('crm-supervisor',))
    accepted = set_status(client, task['id'], 'completed', version=task['version'])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'completed'


def test_returning_to_in_progress_requires_a_comment(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client, approval_required=True)
    task = set_status(client, task['id'], 'in_progress', version=task['version']).json()
    task = set_status(client, task['id'], 'awaiting_review', version=task['version']).json()

    no_comment = set_status(client, task['id'], 'in_progress', version=task['version'])
    assert no_comment.status_code == 422
    assert no_comment.json()['details'][0]['field'] == 'comment'

    returned = set_status(client, task['id'], 'in_progress', comment='Нужно уточнить детали', version=task['version'])
    assert returned.status_code == 200, returned.text
    assert returned.json()['status'] == 'in_progress'


def test_reopen_requires_manager_and_plain_assignee_cannot(client, keycloak, database_url):
    assignee = login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='a@demo.local')
    assignee_id = assignee['user']['id']
    client.cookies.clear()

    login(client, keycloak, subject='kc-super', roles=('crm-supervisor',))
    task = create_task(client, assignee_ids=[assignee_id])
    task = set_status(client, task['id'], 'in_progress', version=task['version']).json()
    task = set_status(client, task['id'], 'completed', version=task['version']).json()
    client.cookies.clear()

    login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='a@demo.local')
    denied = set_status(client, task['id'], 'in_progress', version=task['version'])
    assert denied.status_code == 403

    client.cookies.clear()
    login(client, keycloak, subject='kc-super', roles=('crm-supervisor',))
    reopened = set_status(client, task['id'], 'in_progress', version=task['version'])
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()['status'] == 'in_progress'


def test_invalid_transition_rejected(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)
    response = set_status(client, task['id'], 'completed', version=task['version'])
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'to_status'


def test_completion_blocked_by_required_checklist_item(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)
    item = client.post(f"/api/v1/tasks/{task['id']}/checklist-items", json={'title': 'Проверить документы'}).json()
    task = set_status(client, task['id'], 'in_progress', version=task['version']).json()

    blocked = set_status(client, task['id'], 'completed', version=task['version'])
    assert blocked.status_code == 422
    assert blocked.json()['details'][0]['field'] == 'checklist'

    client.patch(f"/api/v1/checklist-items/{item['id']}", json={'is_done': True})
    ok = set_status(client, task['id'], 'completed', version=task['version'])
    assert ok.status_code == 200, ok.text


def test_completion_blocked_by_open_subtask(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    parent = create_task(client, title='Родительская задача')
    child = create_task(client, title='Подзадача', parent_task_id=parent['id'])
    parent = set_status(client, parent['id'], 'in_progress', version=parent['version']).json()

    blocked = set_status(client, parent['id'], 'completed', version=parent['version'])
    assert blocked.status_code == 422
    assert blocked.json()['details'][0]['field'] == 'subtasks'

    child = set_status(client, child['id'], 'in_progress', version=child['version']).json()
    set_status(client, child['id'], 'completed', version=child['version'])
    ok = set_status(client, parent['id'], 'completed', version=parent['version'])
    assert ok.status_code == 200, ok.text


def test_status_change_writes_task_event_and_audit_event(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)
    set_status(client, task['id'], 'in_progress', version=task['version'])

    with database(database_url) as db:
        events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task['id'], TaskEvent.event_type == 'status_change')).all()
        assert len(events) == 1
        assert (events[0].from_value, events[0].to_value) == ('new', 'in_progress')
        audit = db.scalars(select(AuditEvent).where(AuditEvent.action == 'task.status_change')).all()
        assert len(audit) == 1
