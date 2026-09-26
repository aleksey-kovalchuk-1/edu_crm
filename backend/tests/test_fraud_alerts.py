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
