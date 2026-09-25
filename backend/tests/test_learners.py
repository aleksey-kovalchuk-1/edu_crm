from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
import pytest

from app import models
from app.security import TokenCipher
from helpers import database, login


@pytest.fixture
def head(app, keycloak):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-learner-head')
        yield client


@pytest.fixture
def manager(app, keycloak):
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-user',), subject='kc-learner-manager')
        yield client


def test_incomplete_learner_profile_is_saved_and_full_view_is_restricted(head, manager):
    created = head.post('/api/v1/learners', json={
        'last_name': 'Тестов', 'first_name': 'Иван', 'middle_name': 'Иванович',
        'phone': '00123456789', 'email': 'learner@example.test',
    })
    assert created.status_code == 201, created.text
    learner = created.json()
    assert learner['passport_number'] is None
    assert learner['phone'] == '00123456789'
    safe_list = manager.get('/api/v1/learners')
    assert safe_list.status_code == 200
    assert len(safe_list.json()) == 1
    assert 'snils' not in safe_list.json()[0]
    assert 'passport_number' not in safe_list.json()[0]
    assert manager.get(f"/api/v1/learners/{learner['id']}").status_code == 403
    assert head.get(f"/api/v1/learners/{learner['id']}").status_code == 200


def test_sensitive_identifiers_are_encrypted_and_absent_from_audit(head, database_url):
    created = head.post('/api/v1/learners', json={
        'last_name': 'Тестова', 'first_name': 'Мария', 'snils': '001-234-567 89',
        'passport_series': '0011', 'passport_number': '000123',
        'passport_issued_by': 'Тестовое подразделение', 'passport_department_code': '001-001',
        'diploma_series': '0000', 'diploma_number': '000001',
    })
    assert created.status_code == 201, created.text
    learner = created.json()
    assert learner['passport_number'] == '000123'
    assert learner['diploma_series'] == '0000'
    with database(database_url) as db:
        stored = db.get(models.Learner, learner['id'])
        assert stored.snils_encrypted != '001-234-567 89'
        assert stored.passport_number_encrypted != '000123'
        assert stored.diploma_number_encrypted != '000001'
        audit = db.scalar(select(models.AuditEvent).where(models.AuditEvent.action == 'learner.create'))
        assert '000123' not in audit.summary + str(audit.payload)
        assert '001-234-567 89' not in audit.summary + str(audit.payload)


def test_profile_can_be_completed_later_without_losing_contact_fields(head):
    created = head.post('/api/v1/learners', json={'last_name': 'Тестов', 'first_name': 'Иван', 'phone': '0001'}).json()
    updated = head.patch(f"/api/v1/learners/{created['id']}", json={
        'education': 'Высшее', 'diploma_issued_at': '2024-06-30',
        'passport_issued_at': '2020-01-01', 'postal_code': '001234',
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()['phone'] == '0001'
    assert updated.json()['postal_code'] == '001234'
    assert updated.json()['diploma_issued_at'] == '2024-06-30'


def test_document_values_are_not_searchable_or_visible_in_validation_errors(head, manager):
    created = head.post('/api/v1/learners', json={
        'last_name': 'Тестов', 'first_name': 'Иван', 'passport_number': '000123',
    }).json()
    assert manager.get('/api/v1/learners', params={'q': '000123'}).json() == []
    assert manager.patch(f"/api/v1/learners/{created['id']}", json={'first_name': 'Новый'}).status_code == 403
    bad = head.patch(f"/api/v1/learners/{created['id']}", json={'passport_number': 'SECRET-WRONG'})
    assert bad.status_code == 422
    assert 'SECRET-WRONG' not in bad.text
