"""Background job worker process (D-166). Run as `python -m app.worker` (see compose.yaml `worker` service
and `Dockerfile`'s CMD override) — the same image and migrations as the API, a different entrypoint.

Importing the handler modules registers them into `app.jobs.JOB_HANDLERS` as a side effect; add a new
`from . import <handler_module>  # noqa: F401` line here when a new job kind is introduced.
"""
import logging
import signal
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import jobs
from .settings import load_settings, validate_database_url

# Handler modules register themselves into jobs.JOB_HANDLERS on import.
from . import import_jobs  # noqa: F401,E402
from . import document_jobs  # noqa: F401,E402
from . import report_jobs  # noqa: F401,E402

POLL_INTERVAL_SECONDS = 2
LOG = logging.getLogger('worker')

_stopping = False


def _handle_stop(signum, frame):
    global _stopping
    _stopping = True


def run(session_factory):
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    LOG.info('worker started; kinds: %s', sorted(jobs.JOB_HANDLERS))
    while not _stopping:
        with session_factory() as db:
            job = jobs.claim_next(db)
            if job is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            handler = jobs.JOB_HANDLERS.get(job.kind)
            if handler is None:
                jobs.fail(db, job, error=f'no handler registered for job kind {job.kind!r}')
                continue
            LOG.info('running job %s kind=%s', job.id, job.kind)
            try:
                result = handler(db, job)
            except Exception as error:  # noqa: BLE001 - a handler's own failure must not kill the worker
                db.rollback()
                # Re-open on a fresh transaction to record the failure even if the handler left one broken.
                with session_factory() as failure_db:
                    failed = failure_db.get(type(job), job.id)
                    jobs.fail(failure_db, failed, error=error)
                LOG.exception('job %s kind=%s failed', job.id, job.kind)
            else:
                jobs.finish(db, job, result=result)
                LOG.info('job %s kind=%s succeeded', job.id, job.kind)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    settings = load_settings()
    validate_database_url(settings.database_url)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        run(sessionmaker(bind=engine))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
