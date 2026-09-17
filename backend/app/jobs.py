"""Background job queue (D-166): PostgreSQL only, no Redis. See `worker.py` for the run loop.

A handler module registers itself by importing this module and adding to `JOB_HANDLERS` at import time,
e.g. in `import_jobs.py`: `JOB_HANDLERS['import_apply'] = run_import_apply`. `worker.py` imports every
handler module once at startup so the registry is populated before the poll loop starts.

A handler is `def handler(db: Session, job: BackgroundJob) -> dict`: it receives the same job row the
poller claimed (already locked for the duration of one poll iteration, not held across the whole job —
see `claim_next`) and an open session; it does its own commit(s) and returns a JSON-serializable result
dict, or raises to fail the job (the exception's `str()` becomes `BackgroundJob.error`).
"""
from sqlalchemy import select

from .models import BackgroundJob

JOB_HANDLERS = {}


def enqueue(db, kind, payload, *, correlation_id=None, user_id=None):
    """Adds a queued job to the same transaction as the caller's other writes (commit is the caller's)."""
    job = BackgroundJob(kind=kind, payload=payload, correlation_id=correlation_id, created_by_user_id=user_id)
    db.add(job)
    db.flush()
    return job


def claim_next(db):
    """Locks and returns the oldest queued job as `running`, or None. Commits the claim immediately so the
    row is visible as `running` to other pollers right away, even though the handler itself hasn't finished.
    """
    job = db.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.status == 'queued')
        .order_by(BackgroundJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = 'running'
    job.started_at = _now()
    db.commit()
    return job


def finish(db, job, *, result):
    job.status = 'succeeded'
    job.result = result
    job.finished_at = _now()
    db.commit()


def fail(db, job, *, error):
    job.status = 'failed'
    job.error = str(error)[:2000]
    job.finished_at = _now()
    db.commit()


def _now():
    from .models import utcnow
    return utcnow()
