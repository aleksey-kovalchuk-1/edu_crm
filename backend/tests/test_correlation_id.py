"""Correlation ids tie a request's own audit events together (D-156)."""
from sqlalchemy import select

from app.models import AuditEvent
from helpers import login


def test_response_carries_a_fresh_correlation_id_and_audit_events_reuse_it(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    response = client.post('/api/v1/universities', json={'name': 'Корреляция', 'city': 'Москва', 'contact': ''})
    assert response.status_code == 201
    correlation_id = response.headers['x-correlation-id']
    assert correlation_id

    from helpers import database
    with database(database_url) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'university.create'))
        assert event.correlation_id == correlation_id


def test_client_supplied_correlation_id_is_echoed_back(client):
    response = client.get('/api/v1/health', headers={'X-Correlation-Id': 'from-the-client-123'})
    assert response.headers['x-correlation-id'] == 'from-the-client-123'


def test_two_requests_get_different_correlation_ids(client):
    first = client.get('/api/v1/health').headers['x-correlation-id']
    second = client.get('/api/v1/health').headers['x-correlation-id']
    assert first != second
