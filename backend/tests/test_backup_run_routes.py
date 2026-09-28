"""Latest backup run and manual backup requests, beside production's /admin/backups pair history."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent
from helpers import database, login, make_settings

BASE = '/api/v1/admin/backups'


def iso(hours_ago=0.0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')


def run(result='success', hours_ago=1.0, error=None):
    return {'schema': 1, 'trigger': 'scheduled', 'label': 'daily-20260928', 'started_at': iso(hours_ago),
            'finished_at': None if result == 'running' else iso(hours_ago), 'result': result, 'error': error}


@pytest.fixture
def folders(tmp_path):
    status, requests = tmp_path / 'status', tmp_path / 'requests'
    status.mkdir()
    requests.mkdir()
    return status, requests


@pytest.fixture
def su_client(database_url, keycloak, folders):
    status, requests = folders
    settings = make_settings(database_url, backup_status_file=str(status / 'status.json'), backup_request_dir=str(requests))
    with TestClient(create_app(settings, http_client=keycloak.http_client())) as client:
        login(client, keycloak, roles=('crm-admin', 'crm-superadmin'), subject='kc-irina', name='Ирина Руководитель')
        yield client


def write_run(folders, data):
    (folders[0] / 'last-run.json').write_text(data if isinstance(data, str) else json.dumps(data))


@pytest.mark.parametrize('role', ['crm-admin', 'crm-supervisor', 'crm-user'])
def test_only_superadmin(client, keycloak, role):
    login(client, keycloak, roles=(role,))
    assert client.get(f'{BASE}/run').status_code == 403
    assert client.post(f'{BASE}/manual').status_code == 403


def test_the_existing_pair_history_response_is_unchanged(su_client, folders):
    (folders[0] / 'status.json').write_text(json.dumps({'generated_at': iso(), 'backups': []}))
    assert set(su_client.get(BASE).json()) == {'available', 'reason', 'generated_at', 'backups'}


def test_latest_run_states(su_client, folders):
    assert su_client.get(f'{BASE}/run').json()['last_run'] is None  # no run recorded yet
    write_run(folders, run('failure', error='attachments_backup_failed'))
    body = su_client.get(f'{BASE}/run').json()
    assert body['available'] is True and body['last_run']['result'] == 'failure'
    assert body['last_run']['error'] == 'attachments_backup_failed' and body['manual_available'] is True
    write_run(folders, run('running', hours_ago=7))
    assert su_client.get(f'{BASE}/run').json()['last_run']['result'] == 'interrupted'
    write_run(folders, '{not json')
    body = su_client.get(f'{BASE}/run').json()
    assert body['last_run'] is None and body['reason'] == 'unavailable'
    assert str(folders[0]) not in json.dumps(body)


def test_manual_request_creates_one_flag_and_is_audited(su_client, folders, database_url):
    write_run(folders, run())
    response = su_client.post(f'{BASE}/manual')
    assert response.status_code == 202, response.text
    assert set(json.loads((folders[1] / 'request.json').read_text())) == {'requested_at', 'requested_by_user_id'}
    body = su_client.get(f'{BASE}/run').json()
    assert body['pending_request'] is True and body['pending_since'] is not None
    assert su_client.post(f'{BASE}/manual').status_code == 409
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent.action).where(AuditEvent.action == 'backup.manual_requested'))


def test_manual_request_refused_while_running_or_claimed(su_client, folders):
    write_run(folders, run('running', hours_ago=0.1))
    assert su_client.post(f'{BASE}/manual').status_code == 409
    write_run(folders, run())
    (folders[1] / 'processing.json').write_text('{}')
    assert su_client.get(f'{BASE}/run').json()['pending_request'] is True  # claimed by the host agent
    assert su_client.post(f'{BASE}/manual').status_code == 409


def test_pending_since_reports_the_request_age(su_client, folders):
    flag = folders[1] / 'request.json'
    flag.write_text('{}')
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).timestamp()
    os.utime(flag, (old, old))
    since = datetime.fromisoformat(su_client.get(f'{BASE}/run').json()['pending_since'].replace('Z', '+00:00'))
    assert timedelta(minutes=19) < datetime.now(timezone.utc) - since < timedelta(minutes=21)


def test_manual_not_configured_without_a_request_folder(database_url, keycloak, folders):
    settings = make_settings(database_url, backup_status_file=str(folders[0] / 'status.json'))
    with TestClient(create_app(settings, http_client=keycloak.http_client())) as client:
        login(client, keycloak, roles=('crm-admin', 'crm-superadmin'), subject='kc-irina', name='Ирина Руководитель')
        assert client.get(f'{BASE}/run').json()['manual_available'] is False
        assert client.post(f'{BASE}/manual').status_code == 503
