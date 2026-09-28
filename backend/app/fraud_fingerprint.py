"""Keyed document equality checks; raw values never enter alert metadata."""
import base64
import hashlib
import hmac
import re

from sqlalchemy import or_, select, update

from .audit import record_event
from .errors import AppError, ErrorCode
from .fraud_rules import FraudSignal
from .models import FraudAlert, LearnerFingerprint, utcnow


def normalize_snils(value):
    return re.sub(r'\D', '', value or '')


def normalize_passport_pair(series, number):
    return re.sub(r'\D', '', series or '') + re.sub(r'\D', '', number or '') if series and number else ''


def fingerprint(kind, normalized_value, key_bytes):
    # HMAC permits equality checks without putting a reversible document number in alerts.
    # The kind prefix prevents an identical digit string in two document fields from matching.
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


def normalized_record_values(record, cipher):
    return {
        'snils': normalize_snils(_decrypted(record, 'snils', cipher)),
        'passport_pair': normalize_passport_pair(_decrypted(record, 'passport_series', cipher),
                                                   _decrypted(record, 'passport_number', cipher)),
    }


def preview_document_matches(db, values, request, *, learner=None, incoming_learner_id=None,
                             row_number=None, in_file_index=None):
    """Check submitted identifiers without storing a fingerprint or source value."""
    settings = request.app.state.settings
    # Before a complete backfill, a missing stored fingerprint is not evidence that a new
    # document is unique. Keep this comparison off until coverage has been verified.
    if not settings.fraud_match_key or not settings.fraud_match_coverage_complete:
        return []
    cipher = request.app.state.learner_cipher
    def effective(field):
        if field in values:
            return values[field]
        return _decrypted(learner, field, cipher) if learner is not None else ''

    candidates = {
        'snils': normalize_snils(effective('snils')),
        'passport_pair': normalize_passport_pair(effective('passport_series'), effective('passport_number')),
    }
    key = base64.urlsafe_b64decode(settings.fraud_match_key)
    learner_id = incoming_learner_id if incoming_learner_id is not None else learner.id if learner is not None else None
    signals = []
    for kind, value in candidates.items():
        if not value:
            continue
        digest = fingerprint(kind, value, key)
        query = select(LearnerFingerprint).where(
            LearnerFingerprint.kind == kind,
            LearnerFingerprint.key_version == settings.fraud_match_key_version,
            LearnerFingerprint.digest == digest,
        )
        if learner_id is not None and learner_id > 0:
            query = query.where(LearnerFingerprint.learner_id != learner_id)
        for match in db.scalars(query).all():
            signals.append(FraudSignal('document_identifier_reuse', 1, 'high', 'learner',
                                       learner_id if learner_id and learner_id > 0 else None,
                                       match.learner_id, row_number, kind))
        if in_file_index is not None:
            prior_id = in_file_index.get((kind, digest))
            if prior_id is not None and prior_id != learner_id:
                signals.append(FraudSignal('document_identifier_reuse', 1, 'high', 'learner',
                                           learner_id if learner_id and learner_id > 0 else None,
                                           prior_id if prior_id > 0 else None, row_number, kind))
            in_file_index[(kind, digest)] = learner_id
    return signals


def clear_stale_document_alerts(db, learner_id, kind, version, current_digest):
    """Close unresolved pairs that no longer share a current document fingerprint."""
    alerts = db.scalars(select(FraudAlert).where(
        FraudAlert.rule_code == 'document_identifier_reuse', FraudAlert.evidence_kind == kind,
        FraudAlert.status.in_(('open', 'in_review')),
        or_(FraudAlert.entity_id == learner_id, FraudAlert.related_entity_id == learner_id))).all()
    for alert in alerts:
        other_id = alert.related_entity_id if alert.entity_id == learner_id else alert.entity_id
        other = db.get(LearnerFingerprint, (other_id, kind, version)) if other_id is not None else None
        if current_digest and other is not None and other.digest == current_digest:
            continue
        changed_at = utcnow()
        transitioned = db.execute(update(FraudAlert).where(
            FraudAlert.id == alert.id, FraudAlert.updated_at == alert.updated_at,
            FraudAlert.status.in_(('open', 'in_review'))).values(
                status='cleared', resolution_code='data_corrected', reviewed_by_user_id=None,
                reviewed_at=changed_at, updated_at=changed_at).returning(FraudAlert.id)
            .execution_options(synchronize_session=False)).scalar_one_or_none()
        db.expire(alert)
        if transitioned is None:
            continue
        record_event(db, None, None, 'fraud_alert.auto_clear', entity_type='fraud_alert', entity_id=alert.id,
                     summary='Сигнал закрыт после изменения документа',
                     payload={'rule_code': alert.rule_code, 'resolution_code': 'data_corrected'})


def sync_fingerprints(db, record, request):
    settings = request.app.state.settings
    if not settings.fraud_match_key:
        return []
    key = base64.urlsafe_b64decode(settings.fraud_match_key)
    version = settings.fraud_match_key_version
    cipher = request.app.state.learner_cipher
    values = normalized_record_values(record, cipher)
    signals = []
    for kind, value in values.items():
        previous = db.get(LearnerFingerprint, (record.id, kind, version))
        previous_digest = previous.digest if previous is not None else None
        if not value:
            for old in db.scalars(select(LearnerFingerprint).where(
                    LearnerFingerprint.learner_id == record.id, LearnerFingerprint.kind == kind)).all():
                db.delete(old)
            if previous_digest and settings.fraud_match_coverage_complete:
                clear_stale_document_alerts(db, record.id, kind, version, None)
            continue
        digest = fingerprint(kind, value, key)
        row = previous
        if row is None:
            row = LearnerFingerprint(learner_id=record.id, kind=kind, key_version=version, digest=digest)
            db.add(row)
        else:
            row.digest = digest
        if previous_digest and previous_digest != digest and settings.fraud_match_coverage_complete:
            clear_stale_document_alerts(db, record.id, kind, version, digest)
        if settings.fraud_match_coverage_complete:
            matches = db.scalars(select(LearnerFingerprint).where(
                LearnerFingerprint.kind == kind, LearnerFingerprint.key_version == version,
                LearnerFingerprint.digest == digest, LearnerFingerprint.learner_id != record.id)).all()
            for match in matches:
                signals.append(FraudSignal('document_identifier_reuse', 1, 'high', 'learner',
                                           record.id, match.learner_id, None, kind))
    return signals
