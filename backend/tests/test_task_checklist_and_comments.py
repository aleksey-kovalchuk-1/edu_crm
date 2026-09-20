from sqlalchemy import select

from app.models import AuditEvent, TaskEvent
from helpers import database, login


def create_task(client, **overrides):
    body = {'title': 'Задача', **overrides}
    response = client.post('/api/v1/tasks', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def add_item(client, task_id, **overrides):
    body = {'title': 'Пункт', **overrides}
    response = client.post(f'/api/v1/tasks/{task_id}/checklist-items', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_assignee_completes_own_or_unassigned_item_but_not_someone_elses(client, keycloak, database_url):
    assignee = login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='a@demo.local')
    assignee_id = assignee['user']['id']
    client.cookies.clear()

    other = login(client, keycloak, subject='kc-other', roles=('crm-user',), name='Другой', email='o@demo.local')
    other_id = other['user']['id']
    client.cookies.clear()

    login(client, keycloak, subject='kc-super', roles=('crm-supervisor',))
    task = create_task(client, assignee_ids=[assignee_id])
    own_item = add_item(client, task['id'], title='Моя часть', assignee_user_id=assignee_id)
    unassigned_item = add_item(client, task['id'], title='Общая часть')
    others_item = add_item(client, task['id'], title='Чужая часть', assignee_user_id=other_id)
    client.cookies.clear()

    login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='a@demo.local')
    ok_own = client.patch(f"/api/v1/checklist-items/{own_item['id']}", json={'is_done': True})
    assert ok_own.status_code == 200, ok_own.text
    ok_unassigned = client.patch(f"/api/v1/checklist-items/{unassigned_item['id']}", json={'is_done': True})
    assert ok_unassigned.status_code == 200, ok_unassigned.text
    denied = client.patch(f"/api/v1/checklist-items/{others_item['id']}", json={'is_done': True})
    assert denied.status_code == 403


def test_checklist_progress_and_reorder(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)
    first = add_item(client, task['id'], title='Первый')
    second = add_item(client, task['id'], title='Второй')
    assert (first['position'], second['position']) == (0, 1)

    reordered = client.put(f"/api/v1/tasks/{task['id']}/checklist-order", json={'item_ids': [second['id'], first['id']]})
    assert reordered.status_code == 200, reordered.text
    assert [i['id'] for i in reordered.json()] == [second['id'], first['id']]
    assert [i['position'] for i in reordered.json()] == [0, 1]

    client.patch(f"/api/v1/checklist-items/{first['id']}", json={'is_done': True})
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert sum(1 for i in detail['checklist'] if i['is_done']) == 1
    assert len(detail['checklist']) == 2


def test_subtask_cannot_itself_have_a_subtask(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    parent = create_task(client, title='Родитель')
    child = create_task(client, title='Ребёнок', parent_task_id=parent['id'])

    grandchild = client.post('/api/v1/tasks', json={'title': 'Внук', 'parent_task_id': child['id']})
    assert grandchild.status_code == 422
    assert grandchild.json()['details'][0]['field'] == 'parent_task_id'


def test_subtask_creation_requires_edit_rights_on_parent(client, keycloak, database_url):
    login(client, keycloak, subject='kc-super', roles=('crm-supervisor',))
    parent = create_task(client, title='Родитель')
    client.cookies.clear()

    login(client, keycloak, subject='kc-unrelated', roles=('crm-user',), name='Посторонний', email='u@demo.local')
    denied = client.post('/api/v1/tasks', json={'title': 'Подзадача', 'parent_task_id': parent['id']})
    assert denied.status_code == 404


def test_comment_with_attachment_and_activity_feed(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)
    set = client.post(f"/api/v1/tasks/{task['id']}/status", json={'to_status': 'in_progress', 'version': task['version']})
    assert set.status_code == 200, set.text

    response = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        data={'body': 'Проверил документы'},
        files=[('files', ('note.pdf', b'%PDF-1.4 test', 'application/pdf'))],
    )
    assert response.status_code == 201, response.text
    comment = response.json()
    assert comment['body'] == 'Проверил документы'
    assert [a['filename'] for a in comment['attachments']] == ['note.pdf']

    comments = client.get(f"/api/v1/tasks/{task['id']}/comments").json()
    assert len(comments) == 1

    activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
    assert [e['event_type'] for e in activity] == ['comment_added', 'status_change', 'created']

    with database(database_url) as db:
        audit = db.scalars(select(AuditEvent).where(AuditEvent.action == 'task.comment_add')).one()
        assert 'Проверил' not in audit.summary and 'Проверил' not in str(audit.payload)


def test_lists_each_comments_own_author_and_attachments_not_anothers(client, keycloak, database_url):
    """Batch-loaded comment authors/attachments (performance pass) must still map to the right comment."""
    second_author = login(client, keycloak, subject='kc-second', roles=('crm-user',), name='Второй', email='s@demo.local')
    second_id = second_author['user']['id']
    client.cookies.clear()

    first_author = login(client, keycloak, subject='kc-first', roles=('crm-supervisor',), name='Первый', email='f@demo.local')
    task = create_task(client, assignee_ids=[second_id])
    client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        data={'body': 'Первый комментарий'},
        files=[('files', ('first.pdf', b'%PDF-1.4 first', 'application/pdf'))],
    )
    client.cookies.clear()

    login(client, keycloak, subject='kc-second', roles=('crm-user',), name='Второй', email='s@demo.local')
    client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        data={'body': 'Второй комментарий'},
        files=[('files', ('second.pdf', b'%PDF-1.4 second', 'application/pdf'))],
    )

    comments = client.get(f"/api/v1/tasks/{task['id']}/comments").json()
    assert len(comments) == 2
    by_body = {c['body']: c for c in comments}
    assert by_body['Первый комментарий']['author']['id'] == first_author['user']['id']
    assert [a['filename'] for a in by_body['Первый комментарий']['attachments']] == ['first.pdf']
    assert by_body['Второй комментарий']['author']['id'] == second_author['user']['id']
    assert [a['filename'] for a in by_body['Второй комментарий']['attachments']] == ['second.pdf']


def test_empty_comment_without_attachment_rejected(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)
    response = client.post(f"/api/v1/tasks/{task['id']}/comments", data={'body': '   '})
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'body'
