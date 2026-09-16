"""Audit trail of user actions (the specification's "cache of user actions", decisions D-105 and D-131).

Callers add the event to the same database session as the change, before committing, so the change and
its audit record are stored together or not at all.
"""
from .models import AuditEvent

MAX_SUMMARY_LENGTH = 300


def record_event(db, request, actor, action, *, entity_type=None, entity_id=None, summary, payload=None, correlation_id=None):
    """Returns the `AuditEvent` it created (existing callers ignore the return value; T-091's background-job
    handlers use it as a rollback watermark -- see `entity_import.py`).

    `correlation_id` is normally picked up from `request.state` (set by the middleware, D-166); a caller
    with no request -- a background job -- has no request to read it from, so it passes the job's own
    `correlation_id` explicitly here instead.
    """
    event = AuditEvent(
        user_id=actor.id if actor is not None else None,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        summary=summary[:MAX_SUMMARY_LENGTH],
        payload=payload or {},
        ip=request.client.host if request is not None and request.client else None,
        correlation_id=correlation_id if correlation_id is not None else (getattr(request.state, 'correlation_id', None) if request is not None else None),
    )
    db.add(event)
    return event
