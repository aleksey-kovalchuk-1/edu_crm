import pytest
from sqlalchemy import select

from app.models import AuditEvent, Task, TaskEvent, User
from helpers import database, login


def make_extra_user(database_url, *, full_name='Борис Исполнитель', roles=('crm-user',)):
    with database(database_url) as db:
        user = User(keycloak_sub=f'kc-extra-{full_name}', email='', full_name=full_name, roles=list(roles), is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def create_university(client, name='Тестовый вуз'):
    return client.post('/api/v1/universities', json={'name': name, 'city': 'Москва', 'contact': ''}).json()


def create_launch(client, university_id):
    return client.post('/api/v1/launches', json={
        'university_id': university_id, 'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер', 'students': 30, 'deadline': '2026-10-01',
    }).json()


def create_contract(client, university_id):
    direction = client.post('/api/v1/it-directions', json={'name': 'Программирование'}).json()
    product = client.post('/api/v1/it-products', json={'vendor': 'Vendor', 'name': 'Product', 'direction_ids': [direction['id']]}).json()
    return client.post('/api/v1/contracts', json={
        'contract_number': 'C-1', 'university_id': university_id, 'it_product_id': product['id'], 'signed_at': '2026-01-01',
    }).json()


def test_create_standalone_task_with_assignees_and_no_deadline(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-user',))
    assignee_id = make_extra_user(database_url)

    response = client.post('/api/v1/tasks', json={'title': 'Проверить документы', 'assignee_ids': [assignee_id]})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task['title'] == 'Проверить документы'
    assert task['deadline'] is None
    assert task['status'] == 'new'
    assert task['priority'] == 'normal'
    assert task['creator']['id'] == me['user']['id']
    assert [a['id'] for a in task['assignees']] == [assignee_id]
    assert task['university'] is None
    assert task['version'] == 1

    with database(database_url) as db:
        events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task['id'])).all()
        assert [e.event_type for e in events] == ['created']
        audit = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == 'task', AuditEvent.entity_id == str(task['id']))).all()
        assert len(audit) == 1


def test_create_task_linked_to_university_and_matching_interaction(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    launch = create_launch(client, university['id'])

    response = client.post('/api/v1/tasks', json={
        'title': 'Собрать документы', 'university_id': university['id'], 'launch_id': launch['id'],
    })
    assert response.status_code == 201, response.text
    task = response.json()
    assert task['university']['id'] == university['id']
    assert task['interaction']['id'] == launch['id']


def test_interaction_alone_derives_its_university(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    launch = create_launch(client, university['id'])

    response = client.post('/api/v1/tasks', json={'title': 'Собрать документы', 'launch_id': launch['id']})
    assert response.status_code == 201, response.text
    assert response.json()['university']['id'] == university['id']


def test_contradictory_interaction_and_university_rejected(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university_a = create_university(client, 'Вуз А')
    university_b = create_university(client, 'Вуз Б')
    launch = create_launch(client, university_a['id'])

    response = client.post('/api/v1/tasks', json={
        'title': 'x', 'university_id': university_b['id'], 'launch_id': launch['id'],
    })
    assert response.status_code == 422, response.text
    assert response.json()['details'][0]['field'] == 'launch_id'


def test_contradictory_contract_and_university_rejected(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university_a = create_university(client, 'Вуз А')
    university_b = create_university(client, 'Вуз Б')
    contract = create_contract(client, university_a['id'])

    response = client.post('/api/v1/tasks', json={
        'title': 'x', 'university_id': university_b['id'], 'contract_id': contract['id'],
    })
    assert response.status_code == 422, response.text
    assert response.json()['details'][0]['field'] == 'contract_id'


def test_only_supervisor_may_create_on_behalf_of_another_user(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    other_id = make_extra_user(database_url, full_name='Другой Пользователь')

    response = client.post('/api/v1/tasks', json={'title': 'x', 'creator_id': other_id})
    assert response.status_code == 403, response.text


def test_supervisor_may_create_on_behalf_of_another_user(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    other_id = make_extra_user(database_url, full_name='Другой Пользователь')

    response = client.post('/api/v1/tasks', json={'title': 'x', 'creator_id': other_id})
    assert response.status_code == 201, response.text
    assert response.json()['creator']['id'] == other_id


def test_crm_user_cannot_create_task_for_university_outside_scope(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)

    client.cookies.clear()
    login(client, keycloak, subject='kc-scoped-user', roles=('crm-user',), name='Ограниченный Пользователь', email='scoped@demo.local')
    response = client.post('/api/v1/tasks', json={'title': 'x', 'university_id': university['id']})
    assert response.status_code == 404, response.text


def test_list_default_scope_is_mine_and_paginated(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    for i in range(3):
        assert client.post('/api/v1/tasks', json={'title': f'Задача {i}'}).status_code == 201

    response = client.get('/api/v1/tasks', params={'limit': 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['total'] == 3
    assert len(body['items']) == 2

    page2 = client.get('/api/v1/tasks', params={'limit': 2, 'offset': 2}).json()
    assert len(page2['items']) == 1


def test_list_all_scope_forbidden_for_crm_user(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.get('/api/v1/tasks', params={'scope': 'all'})
    assert response.status_code == 403


def test_any_crm_user_can_list_assignable_users(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    other_id = make_extra_user(database_url, full_name='Борис Исполнитель')
    response = client.get('/api/v1/tasks/assignable-users')
    assert response.status_code == 200, response.text
    assert {u['id'] for u in response.json()} >= {other_id}
    assert set(response.json()[0].keys()) == {'id', 'full_name'}


def test_list_invalid_sort_field_rejected(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.get('/api/v1/tasks', params={'sort': 'owner'})
    assert response.status_code == 422


def test_unrelated_user_gets_404_not_403(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    created = client.post('/api/v1/tasks', json={'title': 'Чужая задача'}).json()

    client.cookies.clear()
    login(client, keycloak, subject='kc-user-2', roles=('crm-user',), name='Второй Пользователь', email='second@demo.local')
    assert client.get(f"/api/v1/tasks/{created['id']}").status_code == 404


def test_patch_rejects_stale_version(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    task = client.post('/api/v1/tasks', json={'title': 'Исходное название'}).json()

    first = client.patch(f"/api/v1/tasks/{task['id']}", json={'title': 'Новое название', 'version': task['version']})
    assert first.status_code == 200, first.text
    assert first.json()['version'] == task['version'] + 1

    stale = client.patch(f"/api/v1/tasks/{task['id']}", json={'title': 'Ещё раз', 'version': task['version']})
    assert stale.status_code == 409, stale.text


def test_assignee_cannot_edit_task_only_creator_can(client, keycloak, database_url):
    assignee = login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='assignee@demo.local')
    assignee_id = assignee['user']['id']
    client.cookies.clear()

    login(client, keycloak, roles=('crm-user',))
    task = client.post('/api/v1/tasks', json={'title': 'x', 'assignee_ids': [assignee_id]}).json()
    client.cookies.clear()

    login(client, keycloak, subject='kc-assignee', roles=('crm-user',), name='Исполнитель', email='assignee@demo.local')
    response = client.patch(f"/api/v1/tasks/{task['id']}", json={'title': 'y', 'version': task['version']})
    assert response.status_code == 403


def test_set_members_replaces_assignees(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    a = make_extra_user(database_url, full_name='Первый')
    b = make_extra_user(database_url, full_name='Второй')
    task = client.post('/api/v1/tasks', json={'title': 'x', 'assignee_ids': [a]}).json()

    response = client.put(f"/api/v1/tasks/{task['id']}/members", json={'assignee_ids': [b], 'participant_ids': [], 'observer_ids': []})
    assert response.status_code == 200, response.text
    assert [m['id'] for m in response.json()['assignees']] == [b]


def test_deep_link_returns_same_task(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    created = client.post('/api/v1/tasks', json={'title': 'Глубокая ссылка'}).json()
    fetched = client.get(f"/api/v1/tasks/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()['id'] == created['id']
    assert fetched.json()['title'] == 'Глубокая ссылка'
