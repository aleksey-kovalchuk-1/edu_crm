"""Keyed document equality checks; raw values never enter alert metadata."""
import base64
import hashlib
import hmac
import re

from sqlalchemy import select

from .errors import AppError, ErrorCode
from .fraud_rules import FraudSignal
from .models import LearnerFingerprint


def normalize_snils(value):
    return re.sub(r'\D', '', value or '')


def normalize_passport_pair(series, number):
    return re.sub(r'\D', '', series or '') + re.sub(r'\D', '', number or '') if series and number else ''


def fingerprint(kind, normalized_value, key_bytes):
    return hmac.new(key_bytes, f'{kind}:{normalized_value}'.encode('utf-8'), hashlib.sha256).hexdigest()


def _decrypted(record, field, cipher):
    stored = getattr(record, f'{field}_encrypted')
    if not stored:
        return ''
    if cipher is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Ключ анкеты слушателя не настроен')
    value = cipher.decrypt(stored)
    if value is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось прочитать защищённую анкету')
    return value


def sync_fingerprints(db, record, request):
    settings = request.app.state.settings
    if not settings.fraud_match_key:
        return []
    key = base64.urlsafe_b64decode(settings.fraud_match_key)
    version = settings.fraud_match_key_version
    cipher = request.app.state.learner_cipher
    values = {
        'snils': normalize_snils(_decrypted(record, 'snils', cipher)),
        'passport_pair': normalize_passport_pair(_decrypted(record, 'passport_series', cipher),
                                                   _decrypted(record, 'passport_number', cipher)),
    }
    signals = []
    for kind, value in values.items():
        if not value:
            for old in db.scalars(select(LearnerFingerprint).where(
                    LearnerFingerprint.learner_id == record.id, LearnerFingerprint.kind == kind)).all():
                db.delete(old)
            continue
        digest = fingerprint(kind, value, key)
        row = db.get(LearnerFingerprint, (record.id, kind, version))
        if row is None:
            row = LearnerFingerprint(learner_id=record.id, kind=kind, key_version=version, digest=digest)
            db.add(row)
        else:
            row.digest = digest
        if settings.fraud_match_coverage_complete:
            matches = db.scalars(select(LearnerFingerprint).where(
                LearnerFingerprint.kind == kind, LearnerFingerprint.key_version == version,
                LearnerFingerprint.digest == digest, LearnerFingerprint.learner_id != record.id)).all()
            for match in matches:
                signals.append(FraudSignal('document_identifier_reuse', 1, 'high', 'learner',
                                           record.id, match.learner_id, None, kind))
    return signals
