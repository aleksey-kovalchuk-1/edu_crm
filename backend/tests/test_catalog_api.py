from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent
from helpers import database, login

LAUNCH = {'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер', 'students': 30, 'deadline': '2026-10-01'}


@pytest.fixture
def head(app, keycloak):
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо', email='pavel.demo@demo.local')
        yield client


@pytest.fixture
def manager(app, keycloak):
    with TestClient(app) as client:
        me = login(client, keycloak, roles=('crm-user',), subject='kc-manager', name='Анна Демо')
        client.user_id = me['user']['id']
        yield client


def create_university(head, name='Северный технологический университет', **extra):
    response = head.post('/api/v1/universities', json={'name': name, 'city': 'Санкт-Петербург', **extra})
    assert response.status_code == 201, response.text
    return response.json()


def create_direction(head, name='DevOps'):
    response = head.post('/api/v1/it-directions', json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()


def create_product(head, vendor='РТК ИТ', name='Учебная среда', direction_ids=()):
    response = head.post('/api/v1/it-products', json={'vendor': vendor, 'name': name, 'direction_ids': list(direction_ids)})
    assert response.status_code == 201, response.text
    return response.json()


def assign(head, university_id, *user_ids):
    response = head.put(f'/api/v1/universities/{university_id}/managers', json={'user_ids': list(user_ids)})
    assert response.status_code == 200, response.text
    return response.json()


def contract_payload(university, product, number='Д-2026-001', **extra):
    return {'contract_number': number, 'university_id': university['id'], 'it_product_id': product['id'], 'signed_at': '2026-01-15', **extra}


def test_directions_are_maintained_by_heads_and_readable_by_all(head, manager):
    assert manager.post('/api/v1/it-directions', json={'name': 'QA'}).status_code == 403
    direction = create_direction(head, 'QA')
    assert [item['name'] for item in manager.get('/api/v1/it-directions').json()] == ['QA']

    assert head.patch(f"/api/v1/it-directions/{direction['id']}", json={'is_active': False}).status_code == 200
    assert manager.get('/api/v1/it-directions').json() == []
    assert len(manager.get('/api/v1/it-directions', params={'include_inactive': True}).json()) == 1


def test_duplicate_direction_returns_conflict_with_field(head):
    create_direction(head, 'DevOps')
    response = head.post('/api/v1/it-directions', json={'name': 'DevOps'})
    assert response.status_code == 409
    assert response.json()['details'][0]['field'] == 'name'


def test_products_filter_by_direction_and_reject_unknown_direction(head):
    devops = create_direction(head, 'DevOps')
    qa = create_direction(head, 'QA')
    create_product(head, name='Конвейер', direction_ids=[devops['id']])
    create_product(head, name='Тестовый стенд', direction_ids=[qa['id'], devops['id']])

    only_qa = head.get('/api/v1/it-products', params={'direction_id': qa['id']}).json()
    assert [product['name'] for product in only_qa] == ['Тестовый стенд']
    assert [direction['name'] for direction in only_qa[0]['directions']] == ['DevOps', 'QA']

    response = head.post('/api/v1/it-products', json={'vendor': 'X', 'name': 'Y', 'direction_ids': [99999]})
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'direction_ids'


def test_manager_sees_only_assigned_universities(head, manager):
    assigned = create_university(head, 'Волжский институт цифровых технологий')
    other = create_university(head, 'Уральская инженерная академия')
    assert manager.get('/api/v1/universities').json() == []

    updated = assign(head, assigned['id'], manager.user_id)
    assert [person['full_name'] for person in updated['managers']] == ['Анна Демо']
    assert [university['name'] for university in manager.get('/api/v1/universities').json()] == ['Волжский институт цифровых технологий']
    assert manager.get(f"/api/v1/universities/{other['id']}").status_code == 404
    assert manager.get(f"/api/v1/universities/{other['id']}/contacts").status_code == 404
    assert len(head.get('/api/v1/universities').json()) == 2


def test_university_input_is_validated(head):
    response = head.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва', 'website': 'javascript:alert(1)'})
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'website'
    create_university(head, 'Вуз')
    duplicate = head.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва'})
    assert duplicate.status_code == 409
    assert duplicate.json()['details'][0]['field'] == 'name'


def test_manager_assignment_validates_users_and_is_audited(head, manager, database_url):
    university = create_university(head)
    assert head.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [99999]}).status_code == 422
    assert manager.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [manager.user_id]}).status_code == 403
    assign(head, university['id'], manager.user_id)
    assert assign(head, university['id'])['managers'] == []
    with database(database_url) as db:
        actions = [event.action for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id))]
    assert actions.count('university.managers') == 2


def test_users_list_is_for_heads_and_administrators(head, manager):
    assert manager.get('/api/v1/users').status_code == 403
    names = [user['full_name'] for user in head.get('/api/v1/users', params={'role': 'crm-user'}).json()]
    assert names == ['Анна Демо']


def test_contacts_are_managed_within_scope(head, manager):
    university = create_university(head)
    assert manager.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Иван Демо'}).status_code == 404
    assign(head, university['id'], manager.user_id)

    created = manager.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Иван Демо', 'email': 'ivan@demo.local'})
    assert created.status_code == 201
    duplicate = manager.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Иван Демо'})
    assert duplicate.status_code == 409
    assert duplicate.json()['details'][0]['field'] == 'full_name'
    assert manager.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Пётр', 'email': 'not-an-email'}).status_code == 422

    contact = created.json()
    assert manager.patch(f"/api/v1/university-contacts/{contact['id']}", json={'position': 'Проректор'}).json()['position'] == 'Проректор'


def test_contract_defaults_validity_and_manager(head, manager):
    university = create_university(head)
    product = create_product(head)
    assign(head, university['id'], manager.user_id)

    created = manager.post('/api/v1/contracts', json=contract_payload(university, product))
    assert created.status_code == 201, created.text
    contract = created.json()
    assert contract['valid_until'] == '2027-01-15'
    assert contract['manager'] == {'id': manager.user_id, 'full_name': 'Анна Демо'}
    assert contract['transfer_status_label'] == 'Не начата'

    leap = manager.post('/api/v1/contracts', json=contract_payload(university, product, 'Д-2028-029', signed_at='2028-02-29')).json()
    assert leap['valid_until'] == '2029-02-28'

    by_head = head.post('/api/v1/contracts', json=contract_payload(university, product, 'Д-2026-100')).json()
    assert by_head['manager'] is None


def test_contract_validation_and_scope(head, manager):
    university = create_university(head, 'Свой вуз')
    foreign = create_university(head, 'Чужой вуз')
    product = create_product(head)
    assign(head, university['id'], manager.user_id)
    foreign_contact = head.post(f"/api/v1/universities/{foreign['id']}/contacts", json={'full_name': 'Иван Демо'}).json()

    def error_field(response):
        return response.json()['details'][0]['field']

    too_early = manager.post('/api/v1/contracts', json=contract_payload(university, product, valid_until='2026-01-14'))
    assert too_early.status_code == 422 and error_field(too_early) == 'valid_until'
    wrong_contact = manager.post('/api/v1/contracts', json=contract_payload(university, product, contact_ids=[foreign_contact['id']]))
    assert wrong_contact.status_code == 422 and error_field(wrong_contact) == 'contact_ids'
    unknown_product = manager.post('/api/v1/contracts', json={**contract_payload(university, product), 'it_product_id': 99999})
    assert unknown_product.status_code == 422 and error_field(unknown_product) == 'it_product_id'
    assert manager.post('/api/v1/contracts', json=contract_payload(foreign, product)).status_code == 404

    assert manager.post('/api/v1/contracts', json=contract_payload(university, product)).status_code == 201
    duplicate = manager.post('/api/v1/contracts', json=contract_payload(university, product))
    assert duplicate.status_code == 409 and error_field(duplicate) == 'contract_number'


def test_contract_list_filters_pagination_and_scope(head, manager):
    own = create_university(head, 'Волжский институт цифровых технологий')
    other = create_university(head, 'Уральская инженерная академия')
    devops = create_direction(head, 'DevOps')
    qa = create_direction(head, 'QA')
    pipeline = create_product(head, name='Конвейер', direction_ids=[devops['id']])
    stand = create_product(head, name='Тестовый стенд', direction_ids=[qa['id']])
    assign(head, own['id'], manager.user_id)

    head.post('/api/v1/contracts', json=contract_payload(own, pipeline, 'Д-1', signed_at='2026-01-10', transfer_status='transferred'))
    head.post('/api/v1/contracts', json=contract_payload(own, stand, 'Д-2', signed_at='2026-03-10'))
    head.post('/api/v1/contracts', json=contract_payload(other, pipeline, 'Д-3', signed_at='2026-05-10'))

    everything = head.get('/api/v1/contracts').json()
    assert everything['total'] == 3
    assert [item['contract_number'] for item in everything['items']] == ['Д-3', 'Д-2', 'Д-1']

    mine = manager.get('/api/v1/contracts').json()
    assert mine['total'] == 2
    assert manager.get(f"/api/v1/contracts/{everything['items'][0]['id']}").status_code == 404

    def numbers(**params):
        return [item['contract_number'] for item in head.get('/api/v1/contracts', params=params).json()['items']]

    assert numbers(it_direction_id=devops['id'], sort='contract_number') == ['Д-1', 'Д-3']
    assert numbers(transfer_status='transferred') == ['Д-1']
    assert numbers(signed_from='2026-02-01', signed_to='2026-04-01') == ['Д-2']
    assert numbers(q='уральская') == ['Д-3']
    assert numbers(q='100%') == []
    page = head.get('/api/v1/contracts', params={'limit': 1, 'offset': 1, 'sort': 'signed_at'}).json()
    assert (page['total'], page['limit'], page['offset'], [item['contract_number'] for item in page['items']]) == (3, 1, 1, ['Д-2'])


def test_contract_expiry_flags(head):
    university = create_university(head)
    product = create_product(head)
    today = date.today()
    soon = head.post('/api/v1/contracts', json=contract_payload(
        university, product, 'Д-скоро', signed_at=(today - timedelta(days=300)).isoformat(), valid_until=(today + timedelta(days=10)).isoformat(),
    )).json()
    expired = head.post('/api/v1/contracts', json=contract_payload(
        university, product, 'Д-истёк', signed_at=(today - timedelta(days=400)).isoformat(), valid_until=(today - timedelta(days=1)).isoformat(),
    )).json()
    assert (soon['expires_soon'], soon['is_expired']) == (True, False)
    assert (expired['expires_soon'], expired['is_expired']) == (False, True)


def test_contract_cannot_be_moved_outside_scope(head, manager):
    own = create_university(head, 'Свой вуз')
    foreign = create_university(head, 'Чужой вуз')
    product = create_product(head)
    assign(head, own['id'], manager.user_id)
    contract = manager.post('/api/v1/contracts', json=contract_payload(own, product)).json()
    assert manager.patch(f"/api/v1/contracts/{contract['id']}", json={'university_id': foreign['id']}).status_code == 404
    changed = manager.patch(f"/api/v1/contracts/{contract['id']}", json={'transfer_status': 'in_progress', 'comment': 'Отправлены лицензии'})
    assert changed.status_code == 200
    assert changed.json()['transfer_status_label'] == 'Идёт передача'


def test_contract_changes_are_audited_atomically(head, database_url):
    university = create_university(head)
    product = create_product(head)
    assert head.post('/api/v1/contracts', json=contract_payload(university, product)).status_code == 201
    assert head.post('/api/v1/contracts', json=contract_payload(university, product)).status_code == 409
    with database(database_url) as db:
        actions = [event.action for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id))]
    assert actions == ['university.create', 'it_product.create', 'contract.create']


def test_transfer_statuses(manager):
    assert manager.get('/api/v1/contracts/transfer-statuses').json() == [
        {'value': 'not_started', 'label': 'Не начата'},
        {'value': 'in_progress', 'label': 'Идёт передача'},
        {'value': 'transferred', 'label': 'Передано'},
        {'value': 'cancelled', 'label': 'Отменено'},
    ]


def audit_actions(database_url):
    with database(database_url) as db:
        return [event.action for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id))]


def test_renaming_product_to_existing_name_with_directions_is_a_conflict(head):
    devops = create_direction(head, 'DevOps')
    create_product(head, name='Конвейер')
    other = create_product(head, name='Стенд')
    response = head.patch(f"/api/v1/it-products/{other['id']}", json={'name': 'Конвейер', 'direction_ids': [devops['id']]})
    assert response.status_code == 409
    assert response.json()['details'][0]['field'] == 'name'


def test_manager_can_only_name_themselves_as_contract_manager(head, manager):
    university = create_university(head)
    product = create_product(head)
    assign(head, university['id'], manager.user_id)
    head_id = next(user['id'] for user in head.get('/api/v1/users').json() if user['full_name'] == 'Павел Демо')

    for other_id in (head_id, 99999):
        response = manager.post('/api/v1/contracts', json=contract_payload(university, product, manager_user_id=other_id))
        assert response.status_code == 422
        assert response.json()['details'][0] == {'field': 'manager_user_id', 'message': 'Менеджер может указать ответственным по договору только себя', 'type': 'value_error'}
    contract = manager.post('/api/v1/contracts', json=contract_payload(university, product, manager_user_id=manager.user_id)).json()
    assert manager.patch(f"/api/v1/contracts/{contract['id']}", json={'manager_user_id': head_id}).status_code == 422
    assert head.patch(f"/api/v1/contracts/{contract['id']}", json={'manager_user_id': head_id}).json()['manager']['full_name'] == 'Павел Демо'


def test_moving_a_contract_drops_contacts_of_the_old_university(head):
    first = create_university(head, 'Первый вуз')
    second = create_university(head, 'Второй вуз')
    product = create_product(head)
    contact = head.post(f"/api/v1/universities/{first['id']}/contacts", json={'full_name': 'Иван Демо'}).json()
    contract = head.post('/api/v1/contracts', json=contract_payload(first, product, contact_ids=[contact['id']])).json()
    moved = head.patch(f"/api/v1/contracts/{contract['id']}", json={'university_id': second['id']})
    assert moved.status_code == 200, moved.text
    assert (moved.json()['university']['id'], moved.json()['contacts']) == (second['id'], [])


def test_inactive_records_cannot_be_newly_linked(head):
    university = create_university(head)
    product = create_product(head)
    contact = head.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Иван Демо'}).json()
    contract = head.post('/api/v1/contracts', json=contract_payload(university, product)).json()

    head.patch(f"/api/v1/university-contacts/{contact['id']}", json={'is_active': False})
    assert head.patch(f"/api/v1/contracts/{contract['id']}", json={'contact_ids': [contact['id']]}).status_code == 422

    head.patch(f"/api/v1/it-products/{product['id']}", json={'is_active': False})
    inactive_product = head.post('/api/v1/contracts', json=contract_payload(university, product, 'Д-2'))
    assert inactive_product.status_code == 422 and inactive_product.json()['details'][0]['field'] == 'it_product_id'
    # Existing links stay editable: changing only the status works even though the product is now inactive.
    assert head.patch(f"/api/v1/contracts/{contract['id']}", json={'transfer_status': 'in_progress'}).status_code == 200

    head.patch(f"/api/v1/universities/{university['id']}", json={'is_active': False})
    assert head.post('/api/v1/launches', json={**LAUNCH, 'university_id': university['id']}).status_code == 422


def test_unchanged_updates_write_no_audit_events(head, database_url):
    university = create_university(head)
    direction = create_direction(head)
    product = create_product(head, direction_ids=[direction['id']])
    contract = head.post('/api/v1/contracts', json=contract_payload(university, product)).json()
    before = audit_actions(database_url)

    assert head.patch(f"/api/v1/universities/{university['id']}", json={'name': university['name'], 'city': university['city']}).status_code == 200
    assert head.patch(f"/api/v1/it-directions/{direction['id']}", json={'name': 'DevOps'}).status_code == 200
    assert head.patch(f"/api/v1/it-products/{product['id']}", json={'name': product['name'], 'direction_ids': [direction['id']]}).status_code == 200
    assert head.patch(f"/api/v1/contracts/{contract['id']}", json={'signed_at': '2026-01-15', 'contact_ids': []}).status_code == 200
    assert audit_actions(database_url) == before


def test_contact_audit_events_contain_no_personal_details(head, database_url):
    university = create_university(head)
    contact = head.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Иван Демо', 'email': 'ivan@demo.local', 'phone': '+7 900 000-00-00'}).json()
    head.patch(f"/api/v1/university-contacts/{contact['id']}", json={'phone': '+7 900 111-11-11'})
    with database(database_url) as db:
        events = [event for event in db.scalars(select(AuditEvent)) if event.entity_type == 'university_contact']
    assert len(events) == 2
    for event in events:
        text = f'{event.summary} {event.payload}'
        assert 'Иван' not in text and 'ivan@' not in text and '900' not in text


def test_manager_dashboard_is_scoped_but_yearly_statistics_are_shared(head, manager):
    own = create_university(head, 'Свой вуз')
    create_university(head, 'Чужой вуз')
    assign(head, own['id'], manager.user_id)
    head.post('/api/v1/launches', json={**LAUNCH, 'university_id': own['id']})
    dashboard = manager.get('/api/v1/dashboard').json()
    assert (dashboard['universities'], dashboard['launches']) == (1, 1)
    assert dashboard['annual'] == head.get('/api/v1/dashboard').json()['annual']


def test_out_of_scope_task_cannot_be_changed(head, manager, database_url):
    from app.models import Task
    foreign = create_university(head, 'Чужой вуз')
    launch = head.post('/api/v1/launches', json={**LAUNCH, 'university_id': foreign['id']}).json()
    with database(database_url) as db:
        task = Task(launch_id=launch['id'], university_id=foreign['id'], title='Подготовить договор', deadline=date(2026, 10, 1))
        db.add(task)
        db.commit()
        task_id = task.id
    assert manager.get(f'/api/v1/tasks/{task_id}').status_code == 404
    assert manager.patch(f'/api/v1/tasks/{task_id}', json={'title': 'x', 'version': 1}).status_code == 404
    assert manager.get('/api/v1/tasks', params={'scope': 'all'}).status_code == 403
    assert manager.get('/api/v1/tasks').json()['items'] == []


def test_interactions_and_tasks_follow_manager_scope(head, manager):
    own = create_university(head, 'Свой вуз')
    foreign = create_university(head, 'Чужой вуз')
    assign(head, own['id'], manager.user_id)
    own_launch = head.post('/api/v1/launches', json={**LAUNCH, 'university_id': own['id']}).json()
    foreign_launch = head.post('/api/v1/launches', json={**LAUNCH, 'university_id': foreign['id']}).json()

    assert [launch['id'] for launch in manager.get('/api/v1/launches').json()] == [own_launch['id']]
    assert manager.patch(f"/api/v1/launches/{foreign_launch['id']}", json={'stage': 2}).status_code == 404
    assert manager.get(f"/api/v1/launches/{foreign_launch['id']}/history").status_code == 404
    assert manager.post('/api/v1/launches', json={**LAUNCH, 'university_id': foreign['id']}).status_code == 404
    dashboard = manager.get('/api/v1/dashboard').json()
    assert (dashboard['universities'], dashboard['launches']) == (1, 1)
