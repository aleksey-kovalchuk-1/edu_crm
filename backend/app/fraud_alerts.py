"""Persist review signals without source values or personal identifiers."""
from sqlalchemy import select

from .audit import record_event
from .models import FraudAlert, utcnow


def dedupe_key(signal, batch_id):
    if signal.entity_id is not None:
        entity_ids = [signal.entity_id]
        if signal.rule_code in {'shared_contact', 'document_identifier_reuse'} and signal.related_entity_id is not None:
            entity_ids.append(signal.related_entity_id)
        suffix = ':'.join(str(identifier) for identifier in sorted(entity_ids))
        return f'{signal.rule_code}:v{signal.rule_version}:{signal.evidence_kind or "generic"}:{signal.entity_type}:{suffix}'
    return f'{signal.rule_code}:v{signal.rule_version}:{signal.evidence_kind or "generic"}:batch:{batch_id}:row:{signal.row_number or 0}'


def upsert_alert(db, signal, batch_id):
    key = dedupe_key(signal, batch_id)
    existing = db.scalar(select(FraudAlert).where(FraudAlert.dedupe_key == key))
    if existing is not None:
        if (existing.status == 'cleared' and existing.resolution_code == 'data_corrected'
                and existing.reviewed_by_user_id is None):
            existing.status = 'open'
            existing.resolution_code = None
            existing.reviewed_by_user_id = None
            existing.reviewed_at = None
            existing.updated_at = utcnow()
            record_event(db, None, None, 'fraud_alert.reopened', entity_type='fraud_alert', entity_id=existing.id,
                         summary='Повторный сигнал после исправления данных', payload={'rule_code': signal.rule_code})
        return existing
    alert = FraudAlert(dedupe_key=key, rule_code=signal.rule_code, rule_version=signal.rule_version,
                       evidence_kind=signal.evidence_kind,
                       priority=signal.priority, entity_type=signal.entity_type, entity_id=signal.entity_id,
                       related_entity_id=signal.related_entity_id, batch_id=batch_id, row_number=signal.row_number)
    db.add(alert)
    db.flush()
    return alert
