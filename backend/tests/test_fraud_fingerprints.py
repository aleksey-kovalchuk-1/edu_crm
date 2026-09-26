import base64
from dataclasses import replace

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import models
from app.fraud_fingerprint import fingerprint, normalize_passport_pair, normalize_snils
from app.backfill_fraud_fingerprints import backfill
from app.security import TokenCipher
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
        processed, last_id = backfill(db, settings, cipher, batch_size=1)
        assert processed == 1
        assert backfill(db, settings, cipher, after_id=last_id) == (0, last_id)
        assert db.scalar(select(func.count()).select_from(models.LearnerFingerprint)) == 1
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
