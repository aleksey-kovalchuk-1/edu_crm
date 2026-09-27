from notification_helpers import disable, enable, ensure_user, notifications, sign_in
from test_workflow_api import PDF, default_workflow

LAUNCH_EVENTS = ('launch_stage_changed', 'launch_comment_or_file', 'launch_completed', 'workflow_stages_changed')


def _setup(client, keycloak, database_url, enable_events=LAUNCH_EVENTS):
    anna_id = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    enable(database_url, anna_id, *enable_events)
    disable(database_url, anna_id, 'university_assigned')  # setup assigns Анна; count only interaction events
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = client.post('/api/v1/universities', json={'name': 'Вуз процесса', 'city': 'Москва', 'contact': ''}).json()
    client.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [anna_id]})
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Python', 'product': 'Среда', 'owner': 'Менеджер',
        'students': 5, 'deadline': '2026-10-01'}).json()
    statuses = default_workflow(client)['statuses']
    return anna_id, launch, statuses


def _launch_notifications(database_url, user_id):
    # Creating an interaction also generates its onboarding task plan (task_assigned); count interaction events only.
    return [n for n in notifications(database_url, user_id) if n[1] in LAUNCH_EVENTS]


def _change(client, launch, status_id, comment='', files=None):
    response = client.post(f"/api/v1/launches/{launch['id']}/status-changes",
                           data={'status_id': str(status_id), 'comment': comment}, files=files)
    assert response.status_code == 201, response.text


def test_status_change_notifies_university_managers(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    _change(client, launch, statuses[1]['id'])
    assert _launch_notifications(database_url, anna_id) == [(anna_id, 'launch_stage_changed', 'launch', launch['id'])]


def test_stage_comment_and_file_in_one_action_is_one_notification(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    _change(client, launch, statuses[1]['id'], comment='Подписали протокол',
            files=[('files', ('протокол.pdf', PDF, 'application/pdf'))])
    assert _launch_notifications(database_url, anna_id) == [(anna_id, 'launch_stage_changed', 'launch', launch['id'])]


def test_comment_without_status_change(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    _change(client, launch, launch['status_id'], comment='Уточнили дату')
    assert _launch_notifications(database_url, anna_id) == [(anna_id, 'launch_comment_or_file', 'launch', launch['id'])]


def test_stage_disabled_falls_back_to_the_comment_notification(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    disable(database_url, anna_id, 'launch_stage_changed')
    _change(client, launch, statuses[1]['id'], comment='С комментарием')
    assert _launch_notifications(database_url, anna_id) == [(anna_id, 'launch_comment_or_file', 'launch', launch['id'])]


def test_final_status_is_announced_as_completed(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    final = next(s for s in statuses if s['is_final'])
    _change(client, launch, final['id'], comment='Готово')
    assert _launch_notifications(database_url, anna_id) == [(anna_id, 'launch_completed', 'launch', launch['id'])]


def test_stage_patch_endpoint_also_notifies(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    assert client.patch(f"/api/v1/launches/{launch['id']}", json={'stage': statuses[2]['position']}).status_code == 200
    assert _launch_notifications(database_url, anna_id) == [(anna_id, 'launch_stage_changed', 'launch', launch['id'])]


def test_default_off_events_send_nothing_until_enabled(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url, enable_events=())
    _change(client, launch, statuses[1]['id'], comment='x')
    assert _launch_notifications(database_url, anna_id) == []


def test_workflow_status_edits_notify_managers_with_launches_on_that_workflow(client, keycloak, database_url):
    anna_id, launch, statuses = _setup(client, keycloak, database_url)
    workflow = default_workflow(client)
    added = client.post(f"/api/v1/workflows/{workflow['id']}/statuses", json={'name': 'Новый этап'})
    assert added.status_code == 201, added.text
    renamed = client.patch(f"/api/v1/workflow-statuses/{statuses[1]['id']}", json={'name': 'Переименованный этап'})
    assert renamed.status_code == 200, renamed.text
    got = notifications(database_url, anna_id, 'workflow_stages_changed')
    assert got == [(anna_id, 'workflow_stages_changed', 'launch', launch['id'])] * 2  # two separate actions
