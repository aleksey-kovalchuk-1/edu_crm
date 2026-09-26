"""Persist review signals without source values or personal identifiers."""
from sqlalchemy import select

from .models import FraudAlert


def dedupe_key(signal, batch_id):
    if signal.entity_id is not None:
        entity_ids = [signal.entity_id]
        if signal.rule_code in {'shared_contact', 'document_identifier_reuse'} and signal.related_entity_id is not None:
            entity_ids.append(signal.related_entity_id)
        suffix = ':'.join(str(identifier) for identifier in sorted(entity_ids))
        return f'{signal.rule_code}:v{signal.rule_version}:{signal.entity_type}:{suffix}'
    return f'{signal.rule_code}:v{signal.rule_version}:batch:{batch_id}:row:{signal.row_number or 0}'


def upsert_alert(db, signal, batch_id):
    key = dedupe_key(signal, batch_id)
    existing = db.scalar(select(FraudAlert).where(FraudAlert.dedupe_key == key))
    if existing is not None:
        return existing
    alert = FraudAlert(dedupe_key=key, rule_code=signal.rule_code, rule_version=signal.rule_version,
                       priority=signal.priority, entity_type=signal.entity_type, entity_id=signal.entity_id,
                       related_entity_id=signal.related_entity_id, batch_id=batch_id, row_number=signal.row_number)
    db.add(alert)
    db.flush()
    return alert
