"""Learners, supplier companies, course applications, customer imports (D-235) and fraud alerts (D-236) are
archived (owner decisions 2026-09-28): their API is not served unless CUSTOMER_DATA_ENABLED is set."""
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import load_settings
from helpers import make_settings

ARCHIVED = ['/api/v1/learners', '/api/v1/vendor-companies', '/api/v1/vendor-contacts',
            '/api/v1/course-applications', '/api/v1/customer-imports/history', '/api/v1/fraud-alerts']


def test_archived_customer_data_api_is_not_served_by_default(database_url):
    app = create_app(make_settings(database_url, customer_data_enabled=False))
    paths = set(app.openapi()['paths'])
    with TestClient(app) as client:
        for path in ARCHIVED:
            assert path not in paths
            assert client.get(path).status_code == 404, path


def test_the_archived_api_can_be_switched_back_on(database_url):
    app = create_app(make_settings(database_url, customer_data_enabled=True))
    paths = set(app.openapi()['paths'])
    assert {'/api/v1/learners', '/api/v1/vendor-companies', '/api/v1/course-applications',
            '/api/v1/fraud-alerts'} <= paths


def test_production_settings_keep_the_archive_off_unless_asked(monkeypatch):
    base = {
        'DATABASE_URL': 'postgresql+psycopg://crm:x@db:5432/edu_crm', 'OIDC_ISSUER': 'http://kc/realms/r',
        'OIDC_INTERNAL_BASE_URL': 'http://kc/realms/r', 'OIDC_CLIENT_ID': 'c', 'OIDC_CLIENT_SECRET': 's',
        'PUBLIC_BASE_URL': 'http://localhost', 'SESSION_ENCRYPTION_KEY': 'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=',
    }
    assert load_settings(base).customer_data_enabled is False
    assert load_settings({**base, 'CUSTOMER_DATA_ENABLED': 'true'}).customer_data_enabled is True
