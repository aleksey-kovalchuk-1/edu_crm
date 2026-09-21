from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent
from app.seed import seed_database
from helpers import database, login

LAUNCH = {'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер', 'students': 30, 'deadline': '2026-10-01'}


def recorded_events(database_url):
    with database(database_url) as db:
        return list(db.scalars(select(AuditEvent).order_by(AuditEvent.id)))


def test_each_change_is_recorded_once_with_actor_and_summary(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-supervisor',))
    university = client.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва'}).json()
    launch = client.post('/api/v1/launches', json={**LAUNCH, 'university_id': university['id']}).json()
    assert client.patch(f"/api/v1/launches/{launch['id']}", json={'stage': 2}).status_code == 200

    events = recorded_events(database_url)
    # Creating the launch also auto-generates the default plan's 14 tasks (task.create per task)
    # between university.create and launch.create — see generate_default_plan_for_launch in app/main.py.
    assert [event.action for event in events] == ['university.create'] + ['task.create'] * 14 + ['launch.create', 'launch.stage_change']
    assert {event.user_id for event in events} == {me['user']['id']}
    assert events[0].entity_id == str(university['id'])
    assert events[-2].payload['university_id'] == university['id']
    assert events[-1].payload == {'from': 0, 'to': 2}
    assert events[-1].summary == '«Python»: этап «Поиск контакта» → «Встреча»'
    assert all(event.ip for event in events)


def test_requests_that_change_nothing_or_fail_record_nothing(client, keycloak, database_url):
    seed_database(database_url)
    login(client, keycloak, roles=('crm-supervisor',))
    launch = client.get('/api/v1/launches').json()[0]
    task = client.get('/api/v1/tasks', params={'scope': 'all'}).json()['items'][0]
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()

    assert client.patch(f"/api/v1/launches/{launch['id']}", json={'stage': launch['stage']}).status_code == 200
    assert client.patch(f"/api/v1/tasks/{task['id']}", json={'title': detail['title'], 'version': detail['version']}).status_code == 200
    assert client.post('/api/v1/universities', json={'name': ' ', 'city': 'Москва'}).status_code == 422
    assert client.patch('/api/v1/tasks/999', json={'title': 'x', 'version': 1}).status_code == 404
    assert client.post('/api/v1/launches', json={**LAUNCH, 'university_id': 999}).status_code == 404

    assert recorded_events(database_url) == []


def test_forbidden_request_records_nothing(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    assert client.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва'}).status_code == 403
    assert recorded_events(database_url) == []


def test_task_update_records_before_and_after(client, keycloak, database_url):
    seed_database(database_url)
    login(client, keycloak, roles=('crm-supervisor',))
    task = client.get('/api/v1/tasks', params={'scope': 'all'}).json()['items'][0]
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    new_title = detail['title'] + ' (обновлено)'
    assert client.patch(f"/api/v1/tasks/{task['id']}", json={'title': new_title, 'version': detail['version']}).status_code == 200
    [event] = recorded_events(database_url)
    assert event.action == 'task.update'
    assert event.payload == {'title': {'from': detail['title'], 'to': new_title}}


def test_managers_see_only_their_own_recent_actions(app, keycloak):
    with TestClient(app) as head, TestClient(app) as manager:
        login(head, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо')
        me = login(manager, keycloak, roles=('crm-user',), subject='kc-manager', name='Анна Демо')
        university = head.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва'}).json()
        assert head.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [me['user']['id']]}).status_code == 200
        assert manager.post('/api/v1/launches', json={**LAUNCH, 'university_id': university['id']}).status_code == 201

        mine = manager.get('/api/v1/audit/recent').json()
        # Most-recent-first: the launch itself, then the 14 auto-generated plan tasks it triggered.
        assert [event['action'] for event in mine] == ['launch.create'] + ['task.create'] * 14
        assert mine[0]['user']['full_name'] == 'Анна Демо'

        everyone = head.get('/api/v1/audit/recent').json()
        assert [event['action'] for event in everyone] == ['launch.create'] + ['task.create'] * 14 + ['university.managers', 'university.create']


def test_recent_actions_limit_is_bounded(client, keycloak):
    login(client, keycloak)
    assert client.get('/api/v1/audit/recent', params={'limit': 0}).status_code == 422
    assert client.get('/api/v1/audit/recent', params={'limit': 101}).status_code == 422
    assert client.get('/api/v1/audit/recent', params={'limit': 100}).status_code == 200


def test_recent_actions_require_login(client):
    assert client.get('/api/v1/audit/recent').status_code == 401
