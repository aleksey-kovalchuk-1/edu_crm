from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import workflow_routes
from app.main import create_app
from app.models import Attachment, AuditEvent
from helpers import database, login, make_settings

PDF = b'%PDF-1.4 synthetic test document'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def create_launch(client):
    university = client.post('/api/v1/universities', json={'name': 'Тестовый вуз', 'city': 'Москва', 'contact': ''}).json()
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер', 'students': 30, 'deadline': '2026-10-01',
    }).json()
    return university, launch


def default_workflow(client):
    return next(w for w in client.get('/api/v1/workflows').json() if w['is_default'])


def stored_files(app):
    return list(Path(app.state.settings.attachments_dir).iterdir())


def test_status_change_with_comment_and_files_round_trip(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    _, launch = create_launch(client)
    workflow = default_workflow(client)
    assert len(workflow['statuses']) == 13
    target = workflow['statuses'][2]

    response = client.post(
        f"/api/v1/launches/{launch['id']}/status-changes",
        data={'status_id': str(target['id']), 'comment': '  Встреча назначена, протокол во вложении  '},
        files=[('files', ('протокол.pdf', PDF, 'application/pdf')), ('files', ('photo.png', PNG, 'image/png'))],
    )
    assert response.status_code == 201, response.text
    change = response.json()
    assert change['from_status']['name'] == 'Поиск контакта'
    assert change['to_status'] == {'id': target['id'], 'name': target['name']}
    assert change['comment'] == 'Встреча назначена, протокол во вложении'
    assert change['author']['full_name'] == 'Анна Демо'
    assert [(a['filename'], a['size_bytes']) for a in change['attachments']] == [('протокол.pdf', len(PDF)), ('photo.png', len(PNG))]

    assert client.get('/api/v1/launches').json()[0]['stage'] == 2
    history = client.get(f"/api/v1/launches/{launch['id']}/status-changes").json()
    assert [h['to_status']['name'] for h in history] == [target['name'], 'Поиск контакта']

    download = client.get(f"/api/v1/attachments/{change['attachments'][0]['id']}")
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers['content-type'] == 'application/pdf'
    assert download.headers['content-disposition'].startswith('attachment;')
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert len(stored_files(app)) == 2

    # A comment without a status change is allowed; the audit event never contains the comment text.
    note = client.post(f"/api/v1/launches/{launch['id']}/status-changes", data={'status_id': str(target['id']), 'comment': 'Уточнили дату'})
    assert note.status_code == 201
    with database(database_url) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == 'launch.status_change')).all()
        assert len(events) == 2
        assert all('Уточнили' not in str(e.payload) and 'протокол' not in str(e.payload) for e in events)


def test_rejects_invalid_files_and_statuses_without_storing_anything(app, client, keycloak, database_url, monkeypatch):
    login(client, keycloak, roles=('crm-supervisor',))
    _, launch = create_launch(client)
    workflow = default_workflow(client)
    url = f"/api/v1/launches/{launch['id']}/status-changes"
    status_id = str(workflow['statuses'][1]['id'])

    def post(files=None, **data):
        return client.post(url, data={'status_id': status_id, **data}, files=files)

    exe = post(files=[('files', ('tool.exe', b'MZ\x90\x00', 'application/octet-stream'))])
    assert exe.status_code == 415 and exe.json()['code'] == 'UNSUPPORTED_MEDIA_TYPE'
    disguised = post(files=[('files', ('scan.pdf', PNG, 'application/pdf'))])
    assert disguised.status_code == 415
    # The second file fails after the first was written; the first must be removed again.
    mixed = post(files=[('files', ('ok.pdf', PDF, 'application/pdf')), ('files', ('bad.docx', PDF, 'application/pdf'))])
    assert mixed.status_code == 415
    assert post(files=[('files', (f'{i}.pdf', PDF, 'application/pdf')) for i in range(6)]).status_code == 422
    assert post(comment='я' * 2001).json()['details'][0]['field'] == 'comment'
    monkeypatch.setattr(workflow_routes, 'MAX_ATTACHMENT_BYTES', len(PDF) - 1)
    assert post(files=[('files', ('big.pdf', PDF, 'application/pdf'))]).status_code == 413
    monkeypatch.undo()

    current = str(workflow['statuses'][0]['id'])
    assert client.post(url, data={'status_id': current}).status_code == 422
    other = client.post('/api/v1/workflows', json={'name': 'Другой процесс', 'statuses': ['Первый', 'Второй']}).json()
    assert client.post(url, data={'status_id': str(other['statuses'][1]['id'])}).status_code == 422
    assert client.post('/api/v1/launches/999/status-changes', data={'status_id': status_id}).status_code == 404

    assert stored_files(app) == []
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(Attachment)) == 0
    assert len(client.get(f"/api/v1/launches/{launch['id']}/status-changes").json()) == 1


def test_managers_cannot_reach_other_universities_files(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    _, launch = create_launch(client)
    workflow = default_workflow(client)
    change = client.post(
        f"/api/v1/launches/{launch['id']}/status-changes",
        data={'status_id': str(workflow['statuses'][1]['id'])}, files=[('files', ('a.pdf', PDF, 'application/pdf'))],
    ).json()

    settings = make_settings(database_url, attachments_dir=app.state.settings.attachments_dir)
    with TestClient(create_app(settings, http_client=keycloak.http_client())) as manager:
        login(manager, keycloak, roles=('crm-user',), subject='kc-manager', name='Менеджер Демо', email='manager@demo.local')
        assert manager.get(f"/api/v1/attachments/{change['attachments'][0]['id']}").status_code == 404
        assert manager.get(f"/api/v1/launches/{launch['id']}/status-changes").status_code == 404
        assert manager.post(f"/api/v1/launches/{launch['id']}/status-changes", data={'status_id': str(workflow['statuses'][2]['id'])}).status_code == 404
        assert manager.post('/api/v1/workflows', json={'name': 'Процесс', 'statuses': ['А']}).status_code == 403
        assert manager.patch(f"/api/v1/workflow-statuses/{workflow['statuses'][0]['id']}", json={'name': 'Х'}).status_code == 403


def test_supervisor_edits_workflow_templates(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    _, launch = create_launch(client)
    workflow = default_workflow(client)
    statuses = workflow['statuses']

    assert client.post('/api/v1/workflows', json={'name': 'Пилот', 'statuses': ['А', 'А']}).status_code == 422
    created = client.post('/api/v1/workflows', json={'name': 'Пилот', 'description': 'Короткий', 'statuses': ['Заявка', 'Готово']})
    assert created.status_code == 201
    assert [(s['name'], s['position'], s['is_final']) for s in created.json()['statuses']] == [('Заявка', 0, False), ('Готово', 1, True)]
    assert client.post('/api/v1/workflows', json={'name': 'Пилот', 'statuses': ['Б']}).status_code == 409

    # Renaming changes the name shown everywhere, including earlier history entries.
    renamed = client.patch(f"/api/v1/workflow-statuses/{statuses[0]['id']}", json={'name': 'Первичный контакт'})
    assert renamed.json()['name'] == 'Первичный контакт'
    assert client.get(f"/api/v1/launches/{launch['id']}/status-changes").json()[0]['to_status']['name'] == 'Первичный контакт'
    assert client.get('/api/v1/stages').json()[0] == 'Первичный контакт'
    assert client.patch(f"/api/v1/workflow-statuses/{statuses[1]['id']}", json={'name': 'Первичный контакт'}).status_code == 409

    assert client.patch(f"/api/v1/workflows/{workflow['id']}", json={'is_active': False}).status_code == 409
    in_use = client.patch(f"/api/v1/workflow-statuses/{statuses[0]['id']}", json={'is_active': False})
    assert in_use.status_code == 409 and in_use.json()['details'][0]['field'] == 'is_active'
    assert client.patch(f"/api/v1/workflow-statuses/{statuses[5]['id']}", json={'is_active': False}).json()['is_active'] is False

    added = client.post(f"/api/v1/workflows/{workflow['id']}/statuses", json={'name': 'Продление договора'})
    assert added.status_code == 201 and added.json()['position'] == 13

    order = [s['id'] for s in reversed(default_workflow(client)['statuses'])]
    assert client.put(f"/api/v1/workflows/{workflow['id']}/status-order", json={'status_ids': order[:-1]}).status_code == 422
    reordered = client.put(f"/api/v1/workflows/{workflow['id']}/status-order", json={'status_ids': order}).json()
    assert reordered['statuses'][0]['name'] == 'Продление договора'
    # The launch is still in «Первичный контакт», which is now last; the older stage field follows the position.
    assert client.get('/api/v1/launches').json()[0]['stage'] == 13

    assert client.patch('/api/v1/workflow-statuses/999', json={'name': 'Нет'}).status_code == 404
    assert client.get('/api/v1/workflows/999').status_code in {404, 405}
