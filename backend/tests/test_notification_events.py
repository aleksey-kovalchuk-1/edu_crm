from sqlalchemy import select

from app.models import Notification, University
from helpers import database
from notification_helpers import enable, ensure_user, notifications, sign_in
from test_reports import create_university


def test_manager_assignment_and_removal_notify_the_manager_only(client, keycloak, database_url):
    anna_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    boss = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = create_university(client, 'Вуз назначений')
    path = f"/api/v1/universities/{university['id']}/managers"
    assert client.put(path, json={'user_ids': [anna_id, boss['id']]}).status_code == 200
    assert notifications(database_url) == [(anna_id, 'university_assigned', 'university', university['id'])]
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
