"""List rows carry the at-a-glance context the Задачи list shows (docs/design/tasks.md, list view):
interaction, checklist/subtask progress, comment count and last change — batch-loaded per page."""
from helpers import login


def create_task(client, **overrides):
    response = client.post('/api/v1/tasks', json={'title': 'Задача', **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def create_university(client):
    return client.post('/api/v1/universities', json={'name': 'Тестовый вуз', 'city': 'Москва', 'contact': ''}).json()


def create_launch(client, university_id):
    return client.post('/api/v1/launches', json={
        'university_id': university_id, 'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер',
        'students': 30, 'deadline': '2026-10-01',
    }).json()


def list_items(client, **params):
    response = client.get('/api/v1/tasks', params={'scope': 'all', **params})
    assert response.status_code == 200, response.text
    return response.json()['items']


def test_list_item_summarises_interaction_checklist_subtasks_and_comments(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    launch = create_launch(client, create_university(client)['id'])
    task = create_task(client, title='С контекстом', launch_id=launch['id'])
    for title in ('Первый', 'Второй', 'Третий'):
        assert client.post(f"/api/v1/tasks/{task['id']}/checklist-items", json={'title': title}).status_code == 201
    first = client.get(f"/api/v1/tasks/{task['id']}").json()['checklist'][0]
    assert client.patch(f"/api/v1/checklist-items/{first['id']}", json={'is_done': True}).status_code == 200
    create_task(client, title='Подзадача', parent_task_id=task['id'])
    for body in ('Раз', 'Два'):
        assert client.post(f"/api/v1/tasks/{task['id']}/comments", data={'body': body}).status_code == 201
    bare = create_task(client, title='Без контекста')

    items = {i['id']: i for i in list_items(client)}
    rich = items[task['id']]
    assert rich['interaction'] == {'id': launch['id'], 'program': 'Python'}
    assert rich['checklist_progress'] == {'total': 3, 'completed': 1}
    assert rich['subtasks'] == {'total': 1, 'completed': 0}
    assert rich['comment_count'] == 2
    assert rich['updated_at']

    empty = items[bare['id']]
    assert empty['interaction'] is None
    assert empty['checklist_progress'] == {'total': 0, 'completed': 0}
    assert empty['subtasks'] == {'total': 0, 'completed': 0}
    assert empty['comment_count'] == 0


def test_priority_sort_follows_severity_not_alphabet(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    for priority in ('normal', 'urgent', 'low', 'high'):
        create_task(client, title=priority, priority=priority)

    assert [i['priority'] for i in list_items(client, sort='-priority')] == ['urgent', 'high', 'normal', 'low']
    assert [i['priority'] for i in list_items(client, sort='priority')] == ['low', 'normal', 'high', 'urgent']


def test_sort_by_last_change(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    older = create_task(client, title='Старая')
    create_task(client, title='Новая')
    assert client.patch(f"/api/v1/tasks/{older['id']}", json={'version': older['version'], 'title': 'Изменённая'}).status_code == 200

    assert list_items(client, sort='-updated_at')[0]['id'] == older['id']
