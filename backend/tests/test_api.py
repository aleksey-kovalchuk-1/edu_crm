from fastapi.testclient import TestClient
from app.main import create_app


def client(tmp_path):
    return TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}", seed_demo=False))


def test_university_launch_and_stage_history_persist(tmp_path):
    with client(tmp_path) as c:
        uni = c.post('/api/v1/universities', json={'name': 'Тестовый вуз', 'city': 'Москва', 'contact': 'Координатор'}).json()
        response = c.post('/api/v1/launches', json={'university_id': uni['id'], 'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер', 'students': 30, 'deadline': '2026-10-01'})
        assert response.status_code == 201
        launch = response.json()
        assert c.patch(f"/api/v1/launches/{launch['id']}", json={'stage': 3}).status_code == 200
        assert len(c.get(f"/api/v1/launches/{launch['id']}/history").json()) == 2
    with client(tmp_path) as c:
        assert c.get('/api/v1/launches').json()[0]['stage'] == 3


def test_rejects_invalid_relationship_stage_and_blank_name(tmp_path):
    with client(tmp_path) as c:
        assert c.post('/api/v1/universities', json={'name': '  ', 'city': 'Москва', 'contact': ''}).status_code == 422
        assert c.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'А' * 101}).status_code == 422
        payload = {'university_id': 999, 'program': 'Python', 'owner': 'Менеджер', 'product': 'IDE', 'students': 20, 'deadline': '2026-10-01'}
        assert c.post('/api/v1/launches', json=payload).status_code == 404
        assert c.patch('/api/v1/launches/1', json={'stage': 99}).status_code == 422
        assert c.patch('/api/v1/launches/999', json={'stage': 1}).status_code == 404


def test_demo_tasks_and_dashboard(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'demo.db'}", seed_demo=True)) as c:
        launches = c.get('/api/v1/launches').json()
        assert len(launches) > 0
        task = c.get('/api/v1/tasks').json()[0]
        assert c.patch(f"/api/v1/tasks/{task['id']}", json={'done': True}).json()['done'] is True
        assert c.get('/api/v1/dashboard').json()['students'] == sum(x['students'] for x in launches)
        assert c.get('/api/v1/dashboard').json()['overdue'] == sum(x['overdue'] for x in launches)
        assert c.patch('/api/v1/tasks/999', json={'done': True}).status_code == 404
