from helpers import database, login


def create_task(client, **overrides):
    body = {'title': 'Задача', **overrides}
    response = client.post('/api/v1/tasks', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_list_items_include_version_for_optimistic_planner_drags(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    task = create_task(client)
    assert task['version'] == 1

    items = client.get('/api/v1/tasks').json()['items']
    listed = next(t for t in items if t['id'] == task['id'])
    assert listed['version'] == 1


def test_preferences_partial_updates_do_not_clobber_other_fields(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))

    saved_list = client.put('/api/v1/tasks/preferences', json={'list_columns': ['title', 'deadline']})
    assert saved_list.status_code == 200, saved_list.text
    assert saved_list.json() == {
        'list_columns': ['title', 'deadline'], 'planner_columns': None, 'planner_positions': None, 'filters': None,
    }

    saved_planner = client.put(
        '/api/v1/tasks/preferences',
        json={'planner_columns': ['new', 'in_progress', 'completed']},
    )
    assert saved_planner.status_code == 200, saved_planner.text
    body = saved_planner.json()
    assert body['list_columns'] == ['title', 'deadline']
    assert body['planner_columns'] == ['new', 'in_progress', 'completed']
    assert body['planner_positions'] is None

    saved_positions = client.put(
        '/api/v1/tasks/preferences',
        json={'planner_positions': {'new': [3, 1, 2]}},
    )
    assert saved_positions.status_code == 200, saved_positions.text
    body = saved_positions.json()
    assert body['list_columns'] == ['title', 'deadline']
    assert body['planner_columns'] == ['new', 'in_progress', 'completed']
    assert body['planner_positions'] == {'new': [3, 1, 2]}

    again = client.get('/api/v1/tasks/preferences').json()
    assert again == body
