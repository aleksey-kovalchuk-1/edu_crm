"""Audit trail of user actions (the specification's "cache of user actions", decisions D-105 and D-131).

Callers add the event to the same database session as the change, before committing, so the change and
its audit record are stored together or not at all.
"""
from .models import AuditEvent

MAX_SUMMARY_LENGTH = 300


def record_event(db, request, actor, action, *, entity_type=None, entity_id=None, summary, payload=None):
    db.add(AuditEvent(
        user_id=actor.id if actor is not None else None,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        summary=summary[:MAX_SUMMARY_LENGTH],
        payload=payload or {},
        ip=request.client.host if request is not None and request.client else None,
    ))
