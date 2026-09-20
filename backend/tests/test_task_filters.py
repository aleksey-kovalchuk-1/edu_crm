from datetime import date, timedelta

from app.task_routes import week_bounds
from helpers import database, login


def create_task(client, **overrides):
    body = {'title': 'Задача', **overrides}
    response = client.post('/api/v1/tasks', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, task_id, to_status, version, comment=''):
    response = client.post(f'/api/v1/tasks/{task_id}/status', json={'to_status': to_status, 'comment': comment, 'version': version})
    assert response.status_code == 200, response.text
    return response.json()


def iso(d):
    return d.isoformat()


def test_counters_cover_open_overdue_due_today_review_and_no_deadline(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    today = date.today()
    overdue = create_task(client, deadline=iso(today - timedelta(days=2)))
    due_today = create_task(client, deadline=iso(today))
    no_deadline = create_task(client)
    in_review = create_task(client, approval_required=True, deadline=iso(today + timedelta(days=5)))
    in_review = set_status(client, in_review['id'], 'in_progress', in_review['version'])
    set_status(client, in_review['id'], 'awaiting_review', in_review['version'])
    done = create_task(client, deadline=iso(today - timedelta(days=1)))
    done = set_status(client, done['id'], 'in_progress', done['version'])
    set_status(client, done['id'], 'completed', done['version'])

    counters = client.get('/api/v1/tasks/counters').json()
    assert counters['open'] == 4  # overdue, due_today, no_deadline, in_review (not the completed one)
    assert counters['overdue'] == 1
    assert counters['due_today'] == 1
    assert counters['awaiting_review'] == 1
    assert counters['no_deadline'] == 1


def test_filter_by_status_priority_and_deadline_range(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    today = date.today()
    urgent = create_task(client, priority='urgent', deadline=iso(today + timedelta(days=1)))
    create_task(client, priority='low', deadline=iso(today + timedelta(days=10)))

    by_priority = client.get('/api/v1/tasks', params={'scope': 'all', 'priority': 'urgent'}).json()
    assert [t['id'] for t in by_priority['items']] == [urgent['id']]

    by_range = client.get('/api/v1/tasks', params={
        'scope': 'all', 'deadline_from': iso(today), 'deadline_to': iso(today + timedelta(days=2)),
    }).json()
    assert [t['id'] for t in by_range['items']] == [urgent['id']]

    by_status = client.get('/api/v1/tasks', params={'scope': 'all', 'status': 'new'}).json()
    assert by_status['total'] == 2


def test_filter_by_deadline_preset_overdue(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    today = date.today()
    overdue = create_task(client, deadline=iso(today - timedelta(days=1)))
    create_task(client, deadline=iso(today + timedelta(days=1)))

    response = client.get('/api/v1/tasks', params={'scope': 'all', 'deadline_preset': 'overdue'}).json()
    assert [t['id'] for t in response['items']] == [overdue['id']]


def test_filter_by_deadline_preset_later(client, keycloak, database_url):
    """The 'later' preset (Deadline board's own 6th+7th bucket boundary) lets the board's "show all"
    link for that group reuse the List view's existing filter machinery instead of a dead end."""
    login(client, keycloak, roles=('crm-supervisor',))
    today = date.today()
    _, week_end = week_bounds(today)
    later = create_task(client, deadline=iso(week_end + timedelta(days=8)))
    create_task(client, deadline=iso(week_end + timedelta(days=1)))  # next_week, not later

    response = client.get('/api/v1/tasks', params={'scope': 'all', 'deadline_preset': 'later'}).json()
    assert [t['id'] for t in response['items']] == [later['id']]


def test_filter_by_creator_assignee_and_active(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-supervisor',))
    mine = create_task(client)
    other = login(client, keycloak, subject='kc-other', roles=('crm-user',), name='Другой', email='o@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    theirs = create_task(client, creator_id=other['user']['id'])
    theirs = set_status(client, theirs['id'], 'in_progress', theirs['version'])
    set_status(client, theirs['id'], 'completed', theirs['version'])

    by_creator = client.get('/api/v1/tasks', params={'scope': 'all', 'creator_id': me['user']['id']}).json()
    assert [t['id'] for t in by_creator['items']] == [mine['id']]

    active_only = client.get('/api/v1/tasks', params={'scope': 'all', 'active': 'true'}).json()
    assert theirs['id'] not in [t['id'] for t in active_only['items']]
    completed_only = client.get('/api/v1/tasks', params={'scope': 'all', 'active': 'false'}).json()
    assert [t['id'] for t in completed_only['items']] == [theirs['id']]


def test_filter_by_has_checklist(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    with_checklist = create_task(client)
    client.post(f"/api/v1/tasks/{with_checklist['id']}/checklist-items", json={'title': 'Пункт'})
    create_task(client)

    response = client.get('/api/v1/tasks', params={'scope': 'all', 'has_checklist': 'true'}).json()
    assert [t['id'] for t in response['items']] == [with_checklist['id']]


def test_deadline_groups(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    today = date.today()
    _, week_end = week_bounds(today)
    overdue = create_task(client, title='Просрочена', deadline=iso(today - timedelta(days=3)))
    due_today = create_task(client, title='Сегодня', deadline=iso(today))
    no_deadline = create_task(client, title='Без срока')
    done = create_task(client, title='Завершена', deadline=iso(today - timedelta(days=5)))
    done = set_status(client, done['id'], 'in_progress', done['version'])
    set_status(client, done['id'], 'completed', done['version'])
    # "This week" is (today, week_end] (docs/design/tasks.md, D-172) — on the week's last day (Sunday)
    # that range is empty, so only assert a distinct this-week task on every other day.
    this_week = create_task(client, title='На неделе', deadline=iso(today + timedelta(days=1))) if today < week_end else None

    groups = {g['group']: [t['id'] for t in g['items']] for g in client.get('/api/v1/tasks/deadline-groups', params={'scope': 'all'}).json()}
    assert groups['overdue'] == [overdue['id']]
    assert groups['today'] == [due_today['id']]
    if this_week:
        assert this_week['id'] in groups['this_week']
    else:
        assert groups['this_week'] == []
    assert groups['no_deadline'] == [no_deadline['id']]
    assert groups['completed'] == [done['id']]


def test_preferences_round_trip(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    empty = client.get('/api/v1/tasks/preferences').json()
    assert empty['list_columns'] is None

    saved = client.put('/api/v1/tasks/preferences', json={'list_columns': ['title', 'deadline', 'assignees']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['list_columns'] == ['title', 'deadline', 'assignees']

    again = client.get('/api/v1/tasks/preferences').json()
    assert again['list_columns'] == ['title', 'deadline', 'assignees']


def test_bulk_status_and_deadline_report_per_task_permission_failures(client, keycloak, database_url):
    login(client, keycloak, subject='kc-owner', roles=('crm-user',), name='Владелец', email='ow@demo.local')
    mine_a = create_task(client)
    mine_b = create_task(client)
    client.cookies.clear()

    login(client, keycloak, roles=('crm-supervisor',))
    unrelated = create_task(client)
    client.cookies.clear()

    login(client, keycloak, subject='kc-owner', roles=('crm-user',), name='Владелец', email='ow@demo.local')
    response = client.post('/api/v1/tasks/bulk/deadline', json={
        'task_ids': [mine_a['id'], mine_b['id'], unrelated['id']], 'deadline': None,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body['updated']) == {mine_a['id'], mine_b['id']}
    assert [s['id'] for s in body['skipped']] == [unrelated['id']]


def test_archive_requires_confirmation_flag_and_hides_from_default_scope(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    task = create_task(client)

    without_confirm = client.post('/api/v1/tasks/bulk/archive', json={'task_ids': [task['id']]})
    assert without_confirm.status_code == 422
    assert without_confirm.json()['details'][0]['field'] == 'confirm'

    archived = client.post('/api/v1/tasks/bulk/archive', json={'task_ids': [task['id']], 'confirm': True})
    assert archived.status_code == 200, archived.text
    assert archived.json()['updated'] == [task['id']]

    listing = client.get('/api/v1/tasks', params={'scope': 'all'}).json()
    assert task['id'] not in [t['id'] for t in listing['items']]

    restored = client.post('/api/v1/tasks/bulk/restore', json={'task_ids': [task['id']]})
    assert restored.status_code == 200, restored.text
    listing_again = client.get('/api/v1/tasks', params={'scope': 'all'}).json()
    assert task['id'] in [t['id'] for t in listing_again['items']]
