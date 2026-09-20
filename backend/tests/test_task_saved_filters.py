from helpers import database, login


def test_saves_filters_per_view_scope_without_clobbering_others(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))

    saved_list_mine = client.put('/api/v1/tasks/preferences', json={
        'filters': {'list:mine': {'status': ['new', 'in_progress'], 'priority': ['high'], 'active': True}},
    })
    assert saved_list_mine.status_code == 200, saved_list_mine.text
    assert saved_list_mine.json()['filters'] == {
        'list:mine': {'status': ['new', 'in_progress'], 'priority': ['high'], 'university_id': None, 'deadline_preset': None, 'active': True, 'has_checklist': None},
    }

    saved_deadlines_mine = client.put('/api/v1/tasks/preferences', json={
        'filters': {'deadlines:mine': {'deadline_preset': 'overdue'}},
    })
    assert saved_deadlines_mine.status_code == 200, saved_deadlines_mine.text
    body = saved_deadlines_mine.json()
    # The earlier list:mine entry must still be there (merge, not replace).
    assert body['filters']['list:mine']['status'] == ['new', 'in_progress']
    assert body['filters']['deadlines:mine']['deadline_preset'] == 'overdue'

    saved_list_all = client.put('/api/v1/tasks/preferences', json={
        'filters': {'list:all': {'status': ['completed']}},
    })
    body = saved_list_all.json()
    assert set(body['filters']) == {'list:mine', 'deadlines:mine', 'list:all'}
    assert body['filters']['list:all']['status'] == ['completed']

    again = client.get('/api/v1/tasks/preferences').json()
    assert again['filters'] == body['filters']


def test_overwriting_one_scopes_filters_leaves_other_fields_of_that_entry_replaced_not_merged(client, keycloak, database_url):
    """Saving a new filter set for an already-saved key replaces that one entry wholesale (it's a
    single 'apply these filters' action from the dialog, not a field-by-field patch of old values)."""
    login(client, keycloak, roles=('crm-user',))
    client.put('/api/v1/tasks/preferences', json={'filters': {'list:mine': {'status': ['new'], 'priority': ['high']}}})

    resaved = client.put('/api/v1/tasks/preferences', json={'filters': {'list:mine': {'status': ['completed']}}})
    assert resaved.json()['filters']['list:mine']['status'] == ['completed']
    assert resaved.json()['filters']['list:mine']['priority'] == []


def test_rejects_unknown_view_scope_key(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    response = client.put('/api/v1/tasks/preferences', json={'filters': {'bogus:mine': {}}})
    assert response.status_code == 422


def test_rejects_invalid_status_value(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    response = client.put('/api/v1/tasks/preferences', json={'filters': {'list:mine': {'status': ['not-a-status']}}})
    assert response.status_code == 422


def test_saved_filters_survive_alongside_list_and_planner_preferences(client, keycloak, database_url):
    """Regression for the existing per-field partial-update behaviour (D-181): saving filters must not
    clobber list_columns/planner_columns/planner_positions saved separately, and vice versa."""
    login(client, keycloak, roles=('crm-user',))
    client.put('/api/v1/tasks/preferences', json={'list_columns': ['title', 'deadline']})
    client.put('/api/v1/tasks/preferences', json={'filters': {'list:mine': {'status': ['new']}}})
    final = client.put('/api/v1/tasks/preferences', json={'planner_columns': ['new', 'completed']}).json()

    assert final['list_columns'] == ['title', 'deadline']
    assert final['filters'] == {'list:mine': {'status': ['new'], 'priority': [], 'university_id': None, 'deadline_preset': None, 'active': None, 'has_checklist': None}}
    assert final['planner_columns'] == ['new', 'completed']


def test_ignores_unknown_saved_filter_keys_on_read(client, keycloak, database_url):
    """Defensive read-side sanitisation: a stale/legacy key already in the database (e.g. from a
    dropped scope) must not break the preferences endpoint; it's just dropped from the response."""
    login(client, keycloak, roles=('crm-user',))
    me = client.get('/api/v1/auth/me').json()['user']
    with database(database_url) as db:
        from app.models import TaskUserPreferences
        db.add(TaskUserPreferences(user_id=me['id'], filters={'list:mine': {'status': ['new']}, 'list:observing_legacy': {'status': ['completed']}}))
        db.commit()

    response = client.get('/api/v1/tasks/preferences').json()
    assert response['filters'] == {'list:mine': {'status': ['new']}}
