"""The background job queue itself (app/jobs.py, app/worker.py) -- not any particular job kind, which
belongs to the handler module that registers it (T-091/T-093)."""
from sqlalchemy.orm import Session

from app import jobs
from app.models import BackgroundJob
from app.worker import run
from helpers import database


def test_enqueue_and_claim_runs_oldest_first(database_url):
    with database(database_url) as db:
        first_id = jobs.enqueue(db, 'noop', {'n': 1}).id
        second_id = jobs.enqueue(db, 'noop', {'n': 2}).id
        db.commit()

    with database(database_url) as db:
        claimed = jobs.claim_next(db)
        assert claimed.id == first_id
        assert claimed.status == 'running'
        assert claimed.started_at is not None
        # A second claim must skip the now-running row and take the next queued one.
        claimed2 = jobs.claim_next(db)
        assert claimed2.id == second_id

    with database(database_url) as db:
        assert db.get(BackgroundJob, first_id).status == 'running'


def test_claim_returns_none_when_nothing_queued(database_url):
    with database(database_url) as db:
        assert jobs.claim_next(db) is None


def test_finish_and_fail_record_result_or_error(database_url):
    with database(database_url) as db:
        job_id = jobs.enqueue(db, 'noop', {}).id
        db.commit()
        claimed = jobs.claim_next(db)
        jobs.finish(db, claimed, result={'created': 3})

    with database(database_url) as db:
        record = db.get(BackgroundJob, job_id)
        assert record.status == 'succeeded'
        assert record.result == {'created': 3}
        assert record.finished_at is not None

    with database(database_url) as db:
        job2_id = jobs.enqueue(db, 'noop', {}).id
        db.commit()
        claimed2 = jobs.claim_next(db)
        jobs.fail(db, claimed2, error=ValueError('boom'))

    with database(database_url) as db:
        record2 = db.get(BackgroundJob, job2_id)
        assert record2.status == 'failed'
        assert record2.error == 'boom'


def test_worker_run_loop_dispatches_registered_handler_and_stops_when_idle(database_url, monkeypatch):
    calls = []

    def handler(db: Session, job: BackgroundJob):
        calls.append(job.payload)
        return {'ok': True}

    monkeypatch.setitem(jobs.JOB_HANDLERS, 'test_kind', handler)

    with database(database_url) as db:
        job_id = jobs.enqueue(db, 'test_kind', {'x': 1}).id
        db.commit()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(database_url)
    try:
        session_factory = sessionmaker(bind=engine)

        # run() loops forever by design; make one iteration happen and then stop it, rather than reaching
        # into its internals -- flip the module-level stop flag from inside the handler itself.
        import app.worker as worker_module

        def handler_then_stop(db, job):
            worker_module._stopping = True
            return handler(db, job)

        monkeypatch.setitem(jobs.JOB_HANDLERS, 'test_kind', handler_then_stop)
        worker_module._stopping = False
        run(session_factory)
    finally:
        engine.dispose()
        import app.worker as worker_module
        worker_module._stopping = False

    assert calls == [{'x': 1}]
    with database(database_url) as db:
        assert db.get(BackgroundJob, job_id).status == 'succeeded'


def test_worker_marks_unknown_kind_as_failed_without_crashing(database_url, monkeypatch):
    with database(database_url) as db:
        job_id = jobs.enqueue(db, 'nonexistent_kind', {}).id
        db.commit()

    import app.worker as worker_module
    # There is exactly one queued job; the second poll iteration finds nothing and would otherwise sleep
    # POLL_INTERVAL_SECONDS for real before checking _stopping again.
    monkeypatch.setattr(worker_module, 'POLL_INTERVAL_SECONDS', 0)
    original_claim = jobs.claim_next

    def claim_then_stop(db):
        result = original_claim(db)
        if result is None:
            worker_module._stopping = True
        return result

    monkeypatch.setattr(worker_module.jobs, 'claim_next', claim_then_stop)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(database_url)
    try:
        worker_module._stopping = False
        run(sessionmaker(bind=engine))
    finally:
        engine.dispose()
        worker_module._stopping = False

    with database(database_url) as db:
        record = db.get(BackgroundJob, job_id)
        assert record.status == 'failed'
        assert 'nonexistent_kind' in record.error
