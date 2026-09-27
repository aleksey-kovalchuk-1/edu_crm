import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent
from helpers import database, login, make_settings

BASE = '/api/v1/backups'


def iso(delta_hours=0):
    return (datetime.now(timezone.utc) - timedelta(hours=delta_hours)).strftime('%Y-%m-%dT%H:%M:%SZ')


def report(result='success', finished_hours_ago=1, success_hours_ago=1):
    return {
        'schema': 1, 'updated_at': iso(finished_hours_ago),
        'last_run': {'trigger': 'scheduled', 'label': 'daily-20260927', 'started_at': iso(finished_hours_ago),
                     'finished_at': None if result == 'running' else iso(finished_hours_ago), 'result': result,
                     'verified': True if result == 'success' else None, 'error': None},
        'last_success_at': iso(success_hours_ago) if success_hours_ago is not None else None,
        'pairs': [{'label': 'daily-20260927',
                   'database': {'file': 'edu_crm-20260927T033000Z-daily-20260927.dump.age', 'size_bytes': 2048, 'created_at': iso(1)},
                   'attachments': {'file': 'attachments-20260927T033001Z-daily-20260927.tar.gz.age', 'size_bytes': 4096, 'created_at': iso(1)}}],
        'retention': {'days': 30, 'min_pairs': 7, 'verification_configured': True},
    }


@pytest.fixture
def dirs():
    with tempfile.TemporaryDirectory() as status, tempfile.TemporaryDirectory() as requests:
        yield Path(status), Path(requests)


@pytest.fixture
def bk_client(database_url, keycloak, dirs):
    status, requests = dirs
    app = create_app(make_settings(database_url, backup_status_dir=str(status), backup_request_dir=str(requests)),
                     http_client=keycloak.http_client())
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-superadmin',), subject='kc-irina', name='Ирина Руководитель')
        yield client


def write(dirs, data):
    (dirs[0] / 'status.json').write_text(data if isinstance(data, str) else json.dumps(data))


@pytest.mark.parametrize('role', ['crm-admin', 'crm-supervisor', 'crm-user'])
def test_only_superadmin(client, keycloak, role):
    login(client, keycloak, roles=(role,))
    assert client.get(f'{BASE}/status').status_code == 403
    assert client.post(f'{BASE}/manual').status_code == 403


def test_status_from_the_report(bk_client, dirs):
    write(dirs, report())
    body = bk_client.get(f'{BASE}/status').json()
    assert body['available'] is True and body['stale'] is False and body['pending_request'] is False
    assert body['last_run']['result'] == 'success' and body['last_run']['verified'] is True
    assert body['pairs'][0]['database']['size_bytes'] == 2048 and body['retention']['days'] == 30
    assert str(dirs[0]) not in json.dumps(body)


def test_missing_and_damaged_reports_are_reported_honestly(bk_client, dirs):
    assert bk_client.get(f'{BASE}/status').json() == {'available': False, 'reason': 'no_report', 'last_run': None,
                                                        'last_success_at': None, 'stale': True, 'pairs': [],
                                                        'retention': None, 'pending_request': False,
                                                        'pending_since': None}
    write(dirs, '{not json')
    assert bk_client.get(f'{BASE}/status').json()['reason'] == 'damaged'
    write(dirs, {**report(), 'schema': 99})
    assert bk_client.get(f'{BASE}/status').json()['reason'] == 'damaged'


def test_old_success_is_stale(bk_client, dirs):
    write(dirs, report(finished_hours_ago=40, success_hours_ago=40))
    assert bk_client.get(f'{BASE}/status').json()['stale'] is True


def test_not_configured_without_directories(client, keycloak):
    login(client, keycloak, roles=('crm-superadmin',))
    body = client.get(f'{BASE}/status').json()
    assert body['available'] is False and body['reason'] == 'not_configured'
    assert client.post(f'{BASE}/manual').status_code == 503


def test_manual_request_creates_one_flag_and_is_audited(bk_client, dirs, database_url):
    write(dirs, report())
    response = bk_client.post(f'{BASE}/manual')
    assert response.status_code == 202, response.text
    flag = json.loads((dirs[1] / 'request.json').read_text())
    assert set(flag) == {'requested_at', 'requested_by_user_id'}
    assert bk_client.get(f'{BASE}/status').json()['pending_request'] is True
    assert bk_client.post(f'{BASE}/manual').status_code == 409  # a second click while waiting
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent.action).where(AuditEvent.action == 'backup.manual_requested'))


def test_manual_request_refused_while_a_backup_runs(bk_client, dirs):
    write(dirs, report(result='running', finished_hours_ago=0.1))
    assert bk_client.post(f'{BASE}/manual').status_code == 409
    (dirs[1] / 'processing.json').write_text('{}')
    write(dirs, report())
    assert bk_client.post(f'{BASE}/manual').status_code == 409


def test_a_run_stuck_in_running_for_hours_counts_as_interrupted(bk_client, dirs):
    write(dirs, report(result='running', finished_hours_ago=7))
    body = bk_client.get(f'{BASE}/status').json()
    assert body['last_run']['result'] == 'interrupted'
    assert bk_client.post(f'{BASE}/manual').status_code == 202


def test_a_claimed_request_still_counts_as_pending_with_its_age(bk_client, dirs):
    write(dirs, report())
    (dirs[1] / 'processing.json').write_text('{}')
    body = bk_client.get(f'{BASE}/status').json()
    assert body['pending_request'] is True
    assert body['pending_since'] is not None


def test_pending_since_is_the_request_age(bk_client, dirs):
    write(dirs, report())
    flag = dirs[1] / 'request.json'
    flag.write_text('{}')
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).timestamp()
    os.utime(flag, (old, old))
    since = datetime.fromisoformat(bk_client.get(f'{BASE}/status').json()['pending_since'].replace('Z', '+00:00'))
    assert timedelta(minutes=19) < datetime.now(timezone.utc) - since < timedelta(minutes=21)
