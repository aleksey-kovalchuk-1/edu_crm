import json

from helpers import login, make_settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_backup_status_requires_superadmin(client, keycloak):
    assert client.get('/api/v1/admin/backups').status_code == 401
    login(client, keycloak, roles=('crm-admin',))
    assert client.get('/api/v1/admin/backups').status_code == 403


def test_backup_status_reads_only_sanitized_metadata(database_url, keycloak, tmp_path):
    status_file = tmp_path / 'status.json'
    status_file.write_text(json.dumps({'generated_at': '2026-09-27T12:00:00Z', 'backups': [
        {'created_at': '2026-09-27T12:00:00Z', 'source': 'release',
         'database_bytes': 12, 'attachments_bytes': 34, 'verified': False},
    ]}), encoding='utf-8')
    settings = make_settings(database_url, backup_status_file=str(status_file))
    app = create_app(settings, http_client=keycloak.http_client())
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-superadmin',))
        response = client.get('/api/v1/admin/backups')
        assert response.status_code == 200
        body = response.json()
        assert body['available'] is True
        assert body['backups'][0]['database_bytes'] == 12
        assert str(tmp_path) not in response.text


def test_backup_status_missing_or_malformed_is_explicit(database_url, keycloak, tmp_path):
    status_file = tmp_path / 'missing.json'
    settings = make_settings(database_url, backup_status_file=str(status_file))
    app = create_app(settings, http_client=keycloak.http_client())
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-superadmin',))
        body = client.get('/api/v1/admin/backups').json()
        assert body == {'available': False, 'reason': 'missing', 'generated_at': None, 'backups': []}
        status_file.write_text('not json', encoding='utf-8')
        body = client.get('/api/v1/admin/backups').json()
        assert body['available'] is False and body['reason'] == 'unavailable'
