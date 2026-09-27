"""Interaction analytics use recorded history and enforce the viewer's university scope."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import StatusChange, University
from helpers import database, login

PATH = '/api/v1/analytics/interactions'
PERIOD = {'period_from': '2026-01-01', 'period_to': '2026-03-31', 'time_zone': 'Asia/Tokyo'}


def create_university(client, name):
    response = client.post('/api/v1/universities', json={'name': name, 'city': 'Москва', 'contact': ''})
    assert response.status_code == 201, response.text
    return response.json()['id']


def create_interaction(client, university_id, *, program='Программа', students=12):
    response = client.post('/api/v1/launches', json={
        'university_id': university_id, 'program': program, 'product': 'Платформа',
        'owner': 'Ирина Петрова', 'students': students, 'deadline': '2026-04-01',
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


def set_history_dates(database_url, launch_id, dates):
    with database(database_url) as db:
        changes = list(db.scalars(select(StatusChange).where(StatusChange.launch_id == launch_id).order_by(StatusChange.id)))
        assert len(changes) == len(dates)
        for change, when in zip(changes, dates, strict=True):
            change.created_at = when
        db.commit()


def test_analytics_validates_period_and_timezone_on_server(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    inverted = client.get(PATH, params={**PERIOD, 'period_from': '2026-04-01'})
    assert inverted.status_code == 422
    assert inverted.json()['details'][0]['field'] == 'period_to'
    invalid_zone = client.get(PATH, params={**PERIOD, 'time_zone': 'not/a-zone'})
    assert invalid_zone.status_code == 422


def test_empty_period_returns_empty_states_and_zero_month_slots(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    create_interaction(client, create_university(client, 'Вуз без событий в периоде'))

    response = client.get(PATH, params={**PERIOD, 'period_from': '2040-01-01', 'period_to': '2040-03-31'})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['has_stage_data'] is False
    assert body['has_implementation_data'] is False
    assert [row['count'] for row in body['stages']] == [0, 0, 0, 0, 0]
    assert body['monthly'] == [
        {'month': '2040-01', 'count': 0}, {'month': '2040-02', 'count': 0}, {'month': '2040-03', 'count': 0},
    ]
    assert body['ranking'] == []


def test_analytics_counts_transitions_with_local_month_and_period_boundaries(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university_id = create_university(client, 'Вуз Восток')
    launch_id = create_interaction(client, university_id)
    assert client.patch(f'/api/v1/launches/{launch_id}', json={'stage': 7}).status_code == 200
    assert client.patch(f'/api/v1/launches/{launch_id}', json={'stage': 8}).status_code == 200
    set_history_dates(database_url, launch_id, [
        datetime(2025, 12, 31, 16, tzinfo=timezone.utc),  # 1 Jan in Tokyo.
        datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
        datetime(2026, 1, 31, 16, tzinfo=timezone.utc),  # 1 Feb in Tokyo, implementation.
    ])

    response = client.get(PATH, params=PERIOD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row['count'] for row in body['stages']] == [1, 1, 1, 1, 0]
    assert body['monthly'] == [
        {'month': '2026-01', 'count': 0}, {'month': '2026-02', 'count': 1}, {'month': '2026-03', 'count': 0},
    ]
    assert body['ranking'] == [{'id': university_id, 'name': 'Вуз Восток', 'programs': 1, 'students': 12}]


def test_manager_scope_applies_to_counts_and_rejects_private_university(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    shared_id = create_university(client, 'Общий вуз')
    private_id = create_university(client, 'Чужой вуз')
    shared_launch = create_interaction(client, shared_id, program='Общая программа')
    private_launch = create_interaction(client, private_id, program='Чужая программа')
    with database(database_url) as db:
        db.get(University, shared_id).team_visible_to_managers = True
        db.commit()
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    set_history_dates(database_url, shared_launch, [start])
    set_history_dates(database_url, private_launch, [start])
    login(client, keycloak, roles=('crm-user',), subject='kc-manager', name='Менеджер', email='manager@example.test')

    response = client.get(PATH, params=PERIOD)

    assert response.status_code == 200, response.text
    assert [row['count'] for row in response.json()['stages']] == [1, 0, 0, 0, 0]
    assert response.json()['universities'] == ['Все вузы']
    assert client.get(PATH, params={**PERIOD, 'university_id': private_id}).status_code == 404
    selected = client.get(PATH, params={**PERIOD, 'university_id': shared_id})
    assert selected.status_code == 200
    assert selected.json()['universities'] == ['Общий вуз']
