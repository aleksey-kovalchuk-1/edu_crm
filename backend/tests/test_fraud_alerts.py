import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import models
from helpers import database, login


def test_conflict_alert_is_deduplicated_and_contains_no_source_values(app, keycloak, database_url):
    original = {'Номер заявки': 'SYN-1', 'Курс': 'Учебный курс', 'Номер потока': 'SYN-P1',
                'Фамилия': 'Тестов', 'Имя': 'Иван', 'Телефон': '79000000001',
                'Email': 'learner@example.test'}
    changed = {**original, 'Курс': 'Другой курс'}
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fraud-head')
        for item in (original, changed, changed):
            result = client.post('/api/v1/customer-imports/applications/apply',
                                 files={'file': ('synthetic.json', json.dumps([item]).encode())})
            assert result.status_code == 200, result.text
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.FraudAlert)) == 1
        alert = db.scalar(select(models.FraudAlert))
        assert alert.rule_code == 'application_number_conflict'
        assert alert.status == 'open'
        assert 'SYN-1' not in repr(alert.__dict__)


def test_only_reviewer_can_decide_alert_and_stale_decision_is_rejected(app, keycloak, database_url):
    original = {'Номер заявки': 'SYN-1', 'Курс': 'Учебный курс', 'Номер потока': 'SYN-P1',
                'Фамилия': 'Тестов', 'Имя': 'Иван', 'Телефон': '79000000001'}
    with TestClient(app) as head, TestClient(app) as manager:
        login(head, keycloak, roles=('crm-supervisor',), subject='kc-fraud-reviewer')
        login(manager, keycloak, roles=('crm-user',), subject='kc-fraud-manager')
        for item in (original, {**original, 'Курс': 'Другой курс'}):
            assert head.post('/api/v1/customer-imports/applications/apply',
                             files={'file': ('synthetic.json', json.dumps([item]).encode())}).status_code == 200
        queue = head.get('/api/v1/fraud-alerts')
        assert queue.status_code == 200, queue.text
        alert = queue.json()[0]
        assert alert['priority'] == 'high'
        assert 'SYN-1' not in queue.text
        alert_id = alert['id']
        assert manager.get('/api/v1/fraud-alerts').status_code == 403
        assert manager.get(f'/api/v1/fraud-alerts/{alert_id}').status_code == 403
        assert manager.patch(f'/api/v1/fraud-alerts/{alert_id}', json={
            'status': 'cleared', 'resolution_code': 'false_positive',
            'expected_updated_at': alert['updated_at']}).status_code == 403
        reviewed = head.patch(f'/api/v1/fraud-alerts/{alert_id}', json={
            'status': 'cleared', 'resolution_code': 'false_positive',
            'expected_updated_at': alert['updated_at']})
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()['status'] == 'cleared'
        stale = head.patch(f'/api/v1/fraud-alerts/{alert_id}', json={
            'status': 'confirmed', 'resolution_code': 'confirmed_by_review',
            'expected_updated_at': alert['updated_at']})
        assert stale.status_code == 409
        assert head.get(f'/api/v1/fraud-alerts/{alert_id}').json()['status'] == 'cleared'
        assert head.get('/api/v1/fraud-alerts', params={'status': 'cleared'}).json()[0]['id'] == alert_id
        assert head.get('/api/v1/fraud-alerts/status').json()['document_match'] == 'disabled_no_key'
    with database(database_url) as db:
        events = db.scalars(select(models.AuditEvent).where(models.AuditEvent.action == 'fraud_alert.review')).all()
        assert len(events) == 1
        assert events[0].payload['resolution_code'] == 'false_positive'
        assert 'SYN-1' not in str(events[0].payload)
