from notification_helpers import ensure_user, notifications, sign_in


def _users(database_url):
    return (ensure_user(database_url, 'kc-anna', 'Анна Петрова'), ensure_user(database_url, 'kc-ivan', 'Иван Иванов'),
            ensure_user(database_url, 'kc-olga', 'Ольга Кузнецова'))


def _create(client, **members):
    response = client.post('/api/v1/tasks', json={'title': 'Подготовить договор', 'deadline': '2026-10-10', **members})
    assert response.status_code == 201, response.text
    return response.json()


def _events(database_url, *types):
    return sorted(n for n in notifications(database_url) if not types or n[1] in types)


def test_creating_a_task_notifies_assignees_and_participants_not_observers(client, keycloak, database_url):
    anna, ivan, olga = _users(database_url)
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    task = _create(client, assignee_ids=[anna], participant_ids=[ivan], observer_ids=[olga])
    assert _events(database_url) == sorted([(anna, 'task_assigned', 'task', task['id']), (ivan, 'task_assigned', 'task', task['id'])])


def test_replacing_members_notifies_only_real_changes(client, keycloak, database_url):
    anna, ivan, olga = _users(database_url)
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    task = _create(client, assignee_ids=[anna, ivan])
    response = client.put(f"/api/v1/tasks/{task['id']}/members", json={'assignee_ids': [anna, olga]})
    assert response.status_code == 200, response.text
    got = _events(database_url, 'task_unassigned') + _events(database_url, 'task_assigned')
    assert got == [(ivan, 'task_unassigned', 'task', task['id'])] + sorted(
        [(anna, 'task_assigned', 'task', task['id']), (ivan, 'task_assigned', 'task', task['id']), (olga, 'task_assigned', 'task', task['id'])])
    # Анна stayed an assignee: exactly one "assigned" for her (from creation), none from the replacement.


def test_bulk_member_changes_notify_each_task_once(client, keycloak, database_url):
    anna, ivan, _ = _users(database_url)
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    first, second = _create(client, assignee_ids=[ivan]), _create(client, assignee_ids=[ivan])
    response = client.post('/api/v1/tasks/bulk/members', json={'task_ids': [first['id'], second['id']],
                                                                'add_assignee_ids': [anna], 'remove_assignee_ids': [ivan]})
    assert response.status_code == 200, response.text
    assert _events(database_url, 'task_unassigned') == sorted([(ivan, 'task_unassigned', 'task', t['id']) for t in (first, second)])
    assert [n for n in _events(database_url, 'task_assigned') if n[0] == anna] == sorted(
        [(anna, 'task_assigned', 'task', t['id']) for t in (first, second)])


def test_deadline_change_single_and_bulk(client, keycloak, database_url):
    anna, ivan, _ = _users(database_url)
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    task = _create(client, assignee_ids=[anna], participant_ids=[ivan])
    assert client.patch(f"/api/v1/tasks/{task['id']}", json={'deadline': '2026-11-01', 'version': task['version']}).status_code == 200
    assert client.post('/api/v1/tasks/bulk/deadline', json={'task_ids': [task['id']], 'deadline': '2026-12-01'}).status_code == 200
    assert _events(database_url, 'task_deadline_changed') == sorted([(anna, 'task_deadline_changed', 'task', task['id'])] * 2 +
                                                                    [(ivan, 'task_deadline_changed', 'task', task['id'])] * 2)


def test_comment_notifies_members_and_creator_but_not_its_author(client, keycloak, database_url):
    anna, ivan, _ = _users(database_url)
    boss = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    task = _create(client, assignee_ids=[anna, ivan])
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.post(f"/api/v1/tasks/{task['id']}/comments", data={'body': 'Готово на 80%'}).status_code == 201
    assert _events(database_url, 'task_commented') == sorted([(ivan, 'task_commented', 'task', task['id']),
                                                              (boss['id'], 'task_commented', 'task', task['id'])])


def _status(client, task_id, to_status, comment=''):
    version = client.get(f'/api/v1/tasks/{task_id}').json()['version']
    response = client.post(f'/api/v1/tasks/{task_id}/status', json={'to_status': to_status, 'comment': comment, 'version': version})
    assert response.status_code == 200, response.text


def test_approval_flow_and_closing(client, keycloak, database_url):
    anna, ivan, _ = _users(database_url)
    boss = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    task = client.post('/api/v1/tasks', json={'title': 'Согласовать', 'assignee_ids': [anna], 'participant_ids': [ivan],
                                              'approval_required': True}).json()
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    _status(client, task['id'], 'in_progress')
    _status(client, task['id'], 'awaiting_review')
    assert _events(database_url, 'task_submitted_for_approval') == [(boss['id'], 'task_submitted_for_approval', 'task', task['id'])]
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    _status(client, task['id'], 'completed')
    assert _events(database_url, 'task_review_decided') == sorted([(anna, 'task_review_decided', 'task', task['id']),
                                                                   (ivan, 'task_review_decided', 'task', task['id'])])
    assert _events(database_url, 'task_closed') == []  # the decision already told them


def test_cancelling_notifies_every_member_and_the_creator(client, keycloak, database_url):
    anna, ivan, olga = _users(database_url)
    sign_in(client, keycloak, 'crm-admin', 'kc-adm', 'Админ Системы')
    creator = sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    task = _create(client, assignee_ids=[anna], participant_ids=[ivan], observer_ids=[olga])
    sign_in(client, keycloak, 'crm-admin', 'kc-adm', 'Админ Системы')
    _status(client, task['id'], 'cancelled', comment='Не нужна')
    assert _events(database_url, 'task_closed') == sorted([(u, 'task_closed', 'task', task['id']) for u in (anna, ivan, olga, creator['id'])])
