import base64
import io
from dataclasses import replace

import openpyxl
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app import models
from app.fraud_fingerprint import clear_stale_document_alerts, fingerprint, normalize_passport_pair, normalize_snils
from app.fraud_alerts import upsert_alert
from app.fraud_rules import FraudSignal
from app.backfill_fraud_fingerprints import backfill, verify_coverage
from app.security import TokenCipher
from app.models import utcnow
from helpers import database, login


def test_equal_documents_have_equal_keyed_fingerprints():
    key = b'x' * 32
    assert normalize_snils('001-234-567 89') == '00123456789'
    assert normalize_passport_pair('0011', '000123') == '0011000123'
    assert fingerprint('snils', '00123456789', key) == fingerprint('snils', '00123456789', key)
    assert fingerprint('snils', '00123456789', key) != fingerprint('snils', '00123456780', key)
    cipher = TokenCipher(Fernet.generate_key())
    assert cipher.encrypt('001-234-567 89') != cipher.encrypt('001-234-567 89')


def test_duplicate_document_creates_safe_alert_when_coverage_complete(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-head')
        for number in (1, 2):
            result = client.post('/api/v1/learners', json={
                'last_name': f'Тестов{number}', 'first_name': 'Иван', 'phone': f'7900000000{number}',
                'snils': '001-234-567 89', 'passport_series': '0011', 'passport_number': '000123',
            })
            assert result.status_code == 201, result.text
    with database(database_url) as db:
        fingerprints = db.scalars(select(models.LearnerFingerprint)).all()
        assert len(fingerprints) == 4
        assert len({item.digest for item in fingerprints if item.kind == 'snils'}) == 1
        assert db.scalar(select(func.count()).select_from(models.FraudAlert)) == 2
        assert '00123456789' not in str([item.__dict__ for item in fingerprints])


def test_customer_preview_reports_document_reuse_without_writing(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    book = openpyxl.Workbook()
    book.active.append(['Фамилия', 'Имя', 'Телефон', 'СНИЛС'])
    book.active.append(['Другой', 'Слушатель', '79000000002', '001-234-567 89'])
    output = io.BytesIO()
    book.save(output)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-preview')
        assert client.post('/api/v1/learners', json={'last_name': 'Один', 'first_name': 'Тест',
                                                    'phone': '79000000001', 'snils': '001-234-567 89'}).status_code == 201
        preview = client.post('/api/v1/customer-imports/learners/preview',
                              files={'file': ('synthetic.xlsx', output.getvalue())})
        assert preview.status_code == 200, preview.text
        assert preview.json()['rows'][0]['signals'][0]['rule_code'] == 'document_identifier_reuse'
        assert '00123456789' not in preview.text
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.Learner)) == 1
        assert db.scalar(select(func.count()).select_from(models.FraudAlert)) == 0


def test_customer_preview_detects_document_reuse_within_one_file(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    book = openpyxl.Workbook()
    book.active.append(['Фамилия', 'Имя', 'Телефон', 'СНИЛС'])
    book.active.append(['Первый', 'Слушатель', '79000000001', '001-234-567 89'])
    book.active.append(['Второй', 'Слушатель', '79000000002', '001-234-567 89'])
    output = io.BytesIO()
    book.save(output)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-in-file')
        preview = client.post('/api/v1/customer-imports/learners/preview',
                              files={'file': ('synthetic.xlsx', output.getvalue())})
        assert preview.status_code == 200, preview.text
        assert preview.json()['summary']['valid'] == 2
        assert preview.json()['rows'][0]['signals'] == []
        assert preview.json()['rows'][1]['signals'][0]['rule_code'] == 'document_identifier_reuse'
        assert '00123456789' not in preview.text
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.Learner)) == 0


def test_editing_reused_document_closes_stale_alert_and_recurrence_reopens_it(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-correction')
        for number in (1, 2):
            assert client.post('/api/v1/learners', json={
                'last_name': f'Тестов{number}', 'first_name': 'Иван',
                'snils': '001-234-567 89'}).status_code == 201
        with database(database_url) as db:
            alert_id = db.scalar(select(models.FraudAlert.id))
        assert client.patch('/api/v1/learners/2', json={'snils': '001-234-567 80'}).status_code == 200
        assert client.get(f'/api/v1/fraud-alerts/{alert_id}').json()['status'] == 'cleared'
        assert client.get(f'/api/v1/fraud-alerts/{alert_id}').json()['resolution_code'] == 'data_corrected'
        assert client.patch('/api/v1/learners/2', json={'snils': '001-234-567 89'}).status_code == 200
        assert client.get(f'/api/v1/fraud-alerts/{alert_id}').json()['status'] == 'open'
    with database(database_url) as db:
        actions = [event.action for event in db.scalars(select(models.AuditEvent)).all()]
        assert 'fraud_alert.auto_clear' in actions
        assert 'fraud_alert.reopened' in actions


def test_human_document_decision_is_not_reset_by_repeated_match(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-human-review')
        for number in (1, 2):
            assert client.post('/api/v1/learners', json={
                'last_name': f'Тестов{number}', 'first_name': 'Иван',
                'snils': '001-234-567 89'}).status_code == 201
        alert = client.get('/api/v1/fraud-alerts').json()[0]
        review = client.patch(f"/api/v1/fraud-alerts/{alert['id']}", json={
            'status': 'cleared', 'resolution_code': 'data_corrected',
            'expected_updated_at': alert['updated_at']})
        assert review.status_code == 200, review.text
        assert client.patch('/api/v1/learners/2', json={'snils': '001-234-567 89'}).status_code == 200
        assert client.get(f"/api/v1/fraud-alerts/{alert['id']}").json()['status'] == 'cleared'


def test_concurrent_human_decision_wins_over_automatic_clear(app, keycloak, database_url, monkeypatch):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-race')
        for number in (1, 2):
            assert client.post('/api/v1/learners', json={
                'last_name': f'Тестов{number}', 'first_name': 'Иван',
                'snils': '001-234-567 89'}).status_code == 201
    with database(database_url) as db:
        alert_id = db.scalar(select(models.FraudAlert.id))
        original_scalars = db.scalars

        class LoadedRows:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        def concurrent_review(statement, *args, **kwargs):
            rows = original_scalars(statement, *args, **kwargs).all()
            with database(database_url) as reviewer:
                reviewer.execute(update(models.FraudAlert).where(models.FraudAlert.id == alert_id).values(
                    status='confirmed', resolution_code='confirmed_by_review', updated_at=utcnow()))
                reviewer.commit()
            return LoadedRows(rows)

        monkeypatch.setattr(db, 'scalars', concurrent_review)
        clear_stale_document_alerts(db, 2, 'snils', 1, None)
        db.commit()
    with database(database_url) as db:
        assert db.get(models.FraudAlert, alert_id).status == 'confirmed'
        assert db.scalar(select(func.count()).select_from(models.AuditEvent).where(
            models.AuditEvent.action == 'fraud_alert.auto_clear')) == 0


def test_concurrent_review_wins_over_automatic_reopen(app, keycloak, database_url, monkeypatch):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    app.state.settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode(),
                                 fraud_match_key_version=1, fraud_match_coverage_complete=True)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-reopen-race')
        for number in (1, 2):
            assert client.post('/api/v1/learners', json={
                'last_name': f'Тестов{number}', 'first_name': 'Иван',
                'snils': '001-234-567 89'}).status_code == 201
        assert client.patch('/api/v1/learners/2', json={'snils': '001-234-567 80'}).status_code == 200
    with database(database_url) as db:
        alert_id = db.scalar(select(models.FraudAlert.id))
        original_scalar = db.scalar

        def concurrent_review(statement, *args, **kwargs):
            alert = original_scalar(statement, *args, **kwargs)
            with database(database_url) as reviewer:
                reviewer.execute(update(models.FraudAlert).where(models.FraudAlert.id == alert_id).values(
                    status='in_review', resolution_code=None, updated_at=utcnow()))
                reviewer.commit()
            return alert

        monkeypatch.setattr(db, 'scalar', concurrent_review)
        upsert_alert(db, FraudSignal('document_identifier_reuse', 1, 'high', 'learner', 2, 1, None, 'snils'), None)
        db.commit()
    with database(database_url) as db:
        assert db.get(models.FraudAlert, alert_id).status == 'in_review'
        assert db.scalar(select(func.count()).select_from(models.AuditEvent).where(
            models.AuditEvent.action == 'fraud_alert.reopened')) == 0


def test_no_fingerprint_key_keeps_normal_learner_editing_available(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-no-key')
        result = client.post('/api/v1/learners', json={'last_name': 'Тестов', 'first_name': 'Иван',
                                                        'snils': '001-234-567 89'})
        assert result.status_code == 201, result.text
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.LearnerFingerprint)) == 0


def test_backfill_is_resumable_and_prints_counts_only(app, keycloak, database_url, capsys):
    cipher = TokenCipher(Fernet.generate_key())
    app.state.learner_cipher = cipher
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-backfill')
        assert client.post('/api/v1/learners', json={'last_name': 'Тестов', 'first_name': 'Иван',
                                                     'snils': '001-234-567 89'}).status_code == 201
    settings = replace(app.state.settings, fraud_match_key=base64.urlsafe_b64encode(b'x' * 32).decode())
    with database(database_url) as db:
        assert verify_coverage(db, settings, cipher)['missing'] == 1
        processed, last_id = backfill(db, settings, cipher, batch_size=1)
        assert processed == 1
        assert backfill(db, settings, cipher, after_id=last_id) == (0, last_id)
        assert db.scalar(select(func.count()).select_from(models.LearnerFingerprint)) == 1
        assert verify_coverage(db, settings, cipher)['missing'] == 0
        db.scalar(select(models.LearnerFingerprint)).digest = '0' * 64
        db.commit()
        assert verify_coverage(db, settings, cipher)['mismatched'] == 1
    assert '001-234-567 89' not in capsys.readouterr().out


def test_key_version_mismatch_does_not_claim_document_match(app, keycloak, database_url):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    key = base64.urlsafe_b64encode(b'x' * 32).decode()
    app.state.settings = replace(app.state.settings, fraud_match_key=key,
                                 fraud_match_key_version=1, fraud_match_coverage_complete=False)
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-fingerprint-version')
        first = client.post('/api/v1/learners', json={'last_name': 'Один', 'first_name': 'Тест',
                                                      'snils': '001-234-567 89'})
        assert first.status_code == 201
        app.state.settings = replace(app.state.settings, fraud_match_key_version=2,
                                     fraud_match_coverage_complete=True)
        second = client.post('/api/v1/learners', json={'last_name': 'Другой', 'first_name': 'Тест',
                                                       'snils': '001-234-567 89'})
        assert second.status_code == 201
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.FraudAlert)) == 0
