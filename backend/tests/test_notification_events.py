from sqlalchemy import select

from app.models import Notification, NotificationPreference, University, User
from helpers import database
from notification_helpers import enable, ensure_user, notifications, sign_in
from test_reports import create_university


def test_creating_university_notifies_every_other_active_manager_without_granting_access(
    client, keycloak, database_url,
):
    anna_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    ivan_id = ensure_user(database_url, 'kc-ivan', 'Иван Иванов')
    inactive_id = ensure_user(database_url, 'kc-inactive', 'Неактивный менеджер')
    with database(database_url) as db:
        inactive = db.get(User, inactive_id)
        inactive.is_active = False
        db.commit()
    actor = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')

    response = client.post('/api/v1/universities', json={'name': 'Новый общий вуз', 'city': 'Москва', 'contact': ''})

    assert response.status_code == 201, response.text
    university_id = response.json()['id']
    assert sorted(notifications(database_url, event_type='university_created')) == [
        (anna_id, 'university_created', 'university', university_id),
        (ivan_id, 'university_created', 'university', university_id),
    ]
    assert all(row[0] != actor['id'] for row in notifications(database_url, event_type='university_created'))
    client.cookies.clear()
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.get(f'/api/v1/universities/{university_id}').status_code == 404
    notice = next(n for n in client.get('/api/v1/notifications').json() if n['event_type'] == 'university_created')
    assert notice['body'] == 'Новый общий вуз'
    assert notice['link'] is None
    assert client.get('/api/v1/notifications/unread-count').json() == {'count': 1}
    client.cookies.clear()
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    assert client.put(f'/api/v1/universities/{university_id}/managers', json={'user_ids': [anna_id]}).status_code == 200
    client.cookies.clear()
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    notice = next(n for n in client.get('/api/v1/notifications').json() if n['event_type'] == 'university_created')
    assert notice['link'] == {'type': 'university', 'id': university_id, 'path': f'/universities/{university_id}'}
    with database(database_url) as db:
        from app.notification_events import _university_events
        _university_events(db, [('new', 'University', {'id': university_id})], actor['id'])
        db.commit()
    assert sorted(notifications(database_url, event_type='university_created')) == [
        (anna_id, 'university_created', 'university', university_id),
        (ivan_id, 'university_created', 'university', university_id),
    ]


def test_creating_university_as_manager_does_not_notify_creator_or_non_managers(
    client, keycloak, database_url,
):
    other_manager_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    ensure_user(database_url, 'kc-admin', 'Администратор', roles=('crm-admin',))
    actor = sign_in(client, keycloak, 'crm-user', 'kc-manager', 'Менеджер')

    response = client.post('/api/v1/universities', json={'name': 'Вуз менеджера', 'city': 'Москва', 'contact': ''})

    assert response.status_code == 201, response.text
    university_id = response.json()['id']
    assert notifications(database_url, event_type='university_created') == [
        (other_manager_id, 'university_created', 'university', university_id),
    ]
    assert all(row[0] != actor['id'] for row in notifications(database_url, event_type='university_created'))
    client.cookies.clear()
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.get(f'/api/v1/universities/{university_id}').status_code == 404
    notice = next(n for n in client.get('/api/v1/notifications').json() if n['event_type'] == 'university_created')
    assert notice['link'] is None


def test_new_university_notification_respects_disabled_preference(client, keycloak, database_url):
    manager_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    other_manager_id = ensure_user(database_url, 'kc-ivan', 'Иван Иванов')
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    with database(database_url) as db:
        db.add(NotificationPreference(user_id=manager_id, event_type='university_created', enabled=False))
        db.commit()

    first = client.post('/api/v1/universities', json={'name': 'Вуз без сигнала', 'city': 'Москва', 'contact': ''})
    assert first.status_code == 201
    assert notifications(database_url, event_type='university_created') == [
        (other_manager_id, 'university_created', 'university', first.json()['id']),
    ]
    assert all(row[0] != manager_id for row in notifications(database_url, event_type='university_created'))


def test_new_university_notification_respects_pause(client, keycloak, database_url):
    from app.notifications import FOREVER
    manager_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    other_manager_id = ensure_user(database_url, 'kc-ivan', 'Иван Иванов')
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    with database(database_url) as db:
        db.get(User, manager_id).notifications_paused_until = FOREVER
        db.commit()
    response = client.post('/api/v1/universities', json={'name': 'Вуз на паузе', 'city': 'Москва', 'contact': ''})
    assert response.status_code == 201
    assert notifications(database_url, event_type='university_created') == [
        (other_manager_id, 'university_created', 'university', response.json()['id']),
    ]
    assert all(row[0] != manager_id for row in notifications(database_url, event_type='university_created'))


def test_updating_university_does_not_create_creation_notification(client, keycloak, database_url):
    ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = create_university(client, 'Существующий вуз')
    before = notifications(database_url, event_type='university_created')
    assert len(before) == 1
    client.patch(f"/api/v1/universities/{university['id']}", json={'city': 'Казань'})
    assert notifications(database_url, event_type='university_created') == before


def test_manager_assignment_and_removal_notify_the_manager_only(client, keycloak, database_url):
    anna_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    boss = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = create_university(client, 'Вуз назначений')
    path = f"/api/v1/universities/{university['id']}/managers"
    assert client.put(path, json={'user_ids': [anna_id, boss['id']]}).status_code == 200
    assert notifications(database_url, event_type='university_assigned') == [
        (anna_id, 'university_assigned', 'university', university['id']),
    ]
    assert client.put(path, json={'user_ids': [boss['id']]}).status_code == 200
    assert notifications(database_url, anna_id, 'university_unassigned') == [(anna_id, 'university_unassigned', 'university', university['id'])]


def test_contact_changes_notify_managers_who_opted_in(client, keycloak, database_url):
    anna_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    ivan_id = ensure_user(database_url, 'kc-ivan', 'Иван Иванов')
    enable(database_url, anna_id, 'university_contacts_changed')  # off by default
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = create_university(client, 'Вуз контактов')
    client.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [anna_id, ivan_id]})
    created = client.post(f"/api/v1/universities/{university['id']}/contacts", json={'full_name': 'Ректор'})
    assert created.status_code == 201, created.text
    client.patch(f"/api/v1/university-contacts/{created.json()['id']}", json={'phone': '+79990000000'})
    got = notifications(database_url, event_type='university_contacts_changed')
    assert got == [(anna_id, 'university_contacts_changed', 'university', university['id'])] * 2  # two actions


def test_the_actor_gets_no_notification_about_their_own_change(client, keycloak, database_url):
    boss = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = create_university(client, 'Вуз самоназначения')
    client.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [boss['id']]})
    assert notifications(database_url) == []


def test_a_rolled_back_transaction_leaves_no_notification(client, keycloak, database_url, app):
    anna_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    with app.state.session_factory() as db:
        university = University(name='Вуз отката', city='Москва', contact='')
        db.add(university)
        db.flush()
        from app.models import UniversityManager
        db.add(UniversityManager(university_id=university.id, user_id=anna_id))
        db.flush()
        db.rollback()
    with database(database_url) as db:
        assert db.scalar(select(Notification)) is None
