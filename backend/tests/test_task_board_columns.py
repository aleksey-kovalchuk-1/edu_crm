from helpers import login


def test_saves_and_returns_custom_planner_columns_and_deadline_board_fields(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))

    saved = client.put('/api/v1/tasks/preferences', json={
        'planner_columns': ['new', 'custom:p1', 'in_progress'],
        'planner_custom_columns': {'custom:p1': {'title': 'Ждём клиента'}},
        'planner_custom_members': {'11': 'custom:p1'},
        'deadline_columns': ['overdue', 'custom:d1', 'today', 'this_week', 'next_week', 'later', 'no_deadline'],
        'deadline_positions': {'overdue': [3, 1, 2]},
        'deadline_custom_columns': {'custom:d1': {'title': 'На согласовании'}},
        'deadline_custom_members': {'42': 'custom:d1'},
    })
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body['planner_columns'] == ['new', 'custom:p1', 'in_progress']
    assert body['planner_custom_columns'] == {'custom:p1': {'title': 'Ждём клиента'}}
    assert body['planner_custom_members'] == {'11': 'custom:p1'}
    assert body['deadline_columns'] == ['overdue', 'custom:d1', 'today', 'this_week', 'next_week', 'later', 'no_deadline']
    assert body['deadline_positions'] == {'overdue': [3, 1, 2]}
    assert body['deadline_custom_columns'] == {'custom:d1': {'title': 'На согласовании'}}
    assert body['deadline_custom_members'] == {'42': 'custom:d1'}

    again = client.get('/api/v1/tasks/preferences').json()
    assert again == body


def test_renaming_a_custom_column_replaces_the_whole_custom_columns_dict(client, keycloak, database_url):
    """Unlike `filters`, the custom-column dicts are plain replace-on-send fields (D-202) — the client
    always has the full current dict loaded from the same query that renders the board, so it sends the
    complete updated dict on every change (add/rename/delete), no server-side merge needed."""
    login(client, keycloak, roles=('crm-user',))
    client.put('/api/v1/tasks/preferences', json={
        'planner_custom_columns': {'custom:a': {'title': 'Первая'}, 'custom:b': {'title': 'Вторая'}},
    })

    renamed = client.put('/api/v1/tasks/preferences', json={
        'planner_custom_columns': {'custom:a': {'title': 'Переименована'}},
    })
    assert renamed.json()['planner_custom_columns'] == {'custom:a': {'title': 'Переименована'}}


def test_rejects_blank_custom_column_title(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    response = client.put('/api/v1/tasks/preferences', json={
        'planner_custom_columns': {'custom:a': {'title': '   '}},
    })
    assert response.status_code == 422


def test_custom_columns_do_not_leak_between_users(client, keycloak, database_url):
    login(client, keycloak, subject='kc-first', roles=('crm-user',), name='Первый', email='f@demo.local')
    client.put('/api/v1/tasks/preferences', json={
        'planner_custom_columns': {'custom:a': {'title': 'Личная колонка'}},
        'deadline_custom_columns': {'custom:d': {'title': 'Личная колонка сроков'}},
    })
    client.cookies.clear()

    login(client, keycloak, subject='kc-second', roles=('crm-user',), name='Второй', email='s@demo.local')
    body = client.get('/api/v1/tasks/preferences').json()
    assert body['planner_custom_columns'] is None
    assert body['deadline_custom_columns'] is None
