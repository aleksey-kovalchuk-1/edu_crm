from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import University
from app.seed import seed_database
from helpers import database, login, make_settings


def test_university_launch_and_stage_history_persist(database_url, keycloak, client):
    login(client, keycloak, roles=('crm-supervisor',))
    uni = client.post('/api/v1/universities', json={'name': 'Тестовый вуз', 'city': 'Москва', 'contact': 'Координатор'}).json()
    response = client.post('/api/v1/launches', json={'university_id': uni['id'], 'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер', 'students': 30, 'deadline': '2026-10-01'})
    assert response.status_code == 201
    launch = response.json()
    assert client.patch(f"/api/v1/launches/{launch['id']}", json={'stage': 3}).status_code == 200
    assert len(client.get(f"/api/v1/launches/{launch['id']}/history").json()) == 2

    # A separate application instance reads the same persisted data.
    with TestClient(create_app(make_settings(database_url), http_client=keycloak.http_client())) as other:
        login(other, keycloak, roles=('crm-supervisor',), subject='kc-user-2')
        assert other.get('/api/v1/launches').json()[0]['stage'] == 3


def test_rejects_invalid_relationship_stage_and_blank_name(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    assert client.post('/api/v1/universities', json={'name': '  ', 'city': 'Москва', 'contact': ''}).status_code == 422
    assert client.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'А' * 101}).status_code == 422
    payload = {'university_id': 999, 'program': 'Python', 'owner': 'Менеджер', 'product': 'IDE', 'students': 20, 'deadline': '2026-10-01'}
    assert client.post('/api/v1/launches', json=payload).status_code == 404
    assert client.patch('/api/v1/launches/1', json={'stage': 99}).status_code == 422
    assert client.patch('/api/v1/launches/999', json={'stage': 1}).status_code == 404


def test_demo_tasks_and_dashboard(database_url, client, keycloak):
    seed_database(database_url)
    login(client, keycloak, roles=('crm-supervisor',))
    launches = client.get('/api/v1/launches').json()
    assert len(launches) > 0
    task = client.post('/api/v1/tasks', json={'title': 'Проверка демо-данных'}).json()
    updated = client.patch(f"/api/v1/tasks/{task['id']}", json={'title': 'Обновлено', 'version': task['version']})
    assert updated.json()['title'] == 'Обновлено'
    assert client.get('/api/v1/dashboard').json()['students'] == sum(x['students'] for x in launches)
    assert client.get('/api/v1/dashboard').json()['overdue'] == sum(x['overdue'] for x in launches)
    assert client.patch('/api/v1/tasks/999', json={'title': 'x', 'version': 1}).status_code == 404


def test_seeding_twice_does_not_duplicate_data(database_url):
    seed_database(database_url)
    seed_database(database_url)
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(University)) == 6
