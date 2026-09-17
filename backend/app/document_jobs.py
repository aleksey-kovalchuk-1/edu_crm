"""Background-job handler for the document quarantine/scan pipeline (T-093, D-165).

`JOB_HANDLERS['document_scan']` scans one `DocumentVersion`'s quarantined file with ClamAV
(`clamd.ClamdNetworkSocket(host=settings.clamav_host, port=settings.clamav_port)`) and transitions its
`state`/`scan_result` per docs/design/file-ingestion-plan.md §5.3:

    quarantined --clean-------------> validated --(same job step)--> linked
    quarantined --infected or error-> rejected

`Validated -> Linked` is performed in this same job run rather than as a separate step: the brief and design
doc describe no manual review gate between a clean scan and the file becoming available, so treating them as
two job runs would only add an extra queue hop with nothing to do in between. Fail closed (D-165): a scanner
hit OR any connection/protocol error rejects the file -- it is never left in `quarantined`/`validated` limbo
that a bug elsewhere could treat as downloadable, and the quarantined bytes are deleted immediately on either
outcome branch. Only a clean scan moves the file out of quarantine.

The scanner is injectable via `scanner_factory(settings) -> scanner` (default: a real `ClamdNetworkSocket`)
so tests substitute `tests/fake_clamd.py` instead of needing a real ClamAV container -- CI does not run one.

Idempotency: this handler is invoked once per claimed `BackgroundJob` row, and `app.jobs.claim_next` already
guarantees a row is claimed by exactly one poller (`SELECT ... FOR UPDATE SKIP LOCKED`), so the normal path
never double-processes a job. As defence in depth against a *second* `document_scan` job somehow being
enqueued for the same version (retry, operator error, a future retry-button), the handler also checks
`version.state` up front and no-ops if it is no longer `quarantined` -- so re-running it never re-scans,
re-moves, or re-transitions a version that was already resolved.
"""
import logging
from pathlib import Path

import clamd

from .audit import record_event
from .jobs import JOB_HANDLERS
from .models import Document, DocumentVersion, User
from .settings import load_settings

LOG = logging.getLogger('document_jobs')


def _default_scanner(settings):
    return clamd.ClamdNetworkSocket(host=settings.clamav_host, port=settings.clamav_port)


def run_document_scan(db, job, *, scanner_factory=_default_scanner, settings=None):
    settings = settings or load_settings()
    version_id = job.payload['document_version_id']
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f'document_version {version_id} not found')
    if version.state != 'quarantined':
        # Already resolved by an earlier run of this same job kind for this version; do nothing further.
        return {'state': version.state, 'scan_result': version.scan_result, 'already_processed': True}

    quarantine_path = Path(settings.documents_dir) / 'quarantine' / version.storage_key
    document = db.get(Document, version.document_id)
    user = db.get(User, job.created_by_user_id) if job.created_by_user_id else None

    try:
        scanner = scanner_factory(settings)
        with open(quarantine_path, 'rb') as handle:
            response = scanner.instream(handle)
    except Exception as error:  # noqa: BLE001 - any connection/scan failure fails closed, never "safe by default"
        LOG.error('document_scan: scanner error for version %s: %s', version_id, error)
        version.state = 'rejected'
        version.scan_result = 'error'
        quarantine_path.unlink(missing_ok=True)
        record_event(
            db, None, user, 'document.scan_error', entity_type='document_version', entity_id=version.id,
            summary=f'Ошибка антивирусной проверки файла «{version.filename}»: файл отклонён',
            payload={'error': str(error)[:500]}, correlation_id=job.correlation_id,
        )
        db.commit()
        return {'state': version.state, 'scan_result': version.scan_result}

    verdict, signature = next(iter(response.values()), (None, None))

    if verdict == 'FOUND':
        version.state = 'rejected'
        version.scan_result = 'infected'
        quarantine_path.unlink(missing_ok=True)
        record_event(
            db, None, user, 'document.scan_infected', entity_type='document_version', entity_id=version.id,
            summary=f'Файл «{version.filename}» отклонён: обнаружена угроза', payload={'signature': signature},
            correlation_id=job.correlation_id,
        )
        db.commit()
        return {'state': version.state, 'scan_result': version.scan_result, 'signature': signature}

    if verdict != 'OK':
        # Any response that is neither a known hit nor a clean verdict is treated the same as a scanner
        # error: fail closed rather than guess.
        LOG.error('document_scan: unexpected clamd verdict %r for version %s', verdict, version_id)
        version.state = 'rejected'
        version.scan_result = 'error'
        quarantine_path.unlink(missing_ok=True)
        record_event(
            db, None, user, 'document.scan_error', entity_type='document_version', entity_id=version.id,
            summary=f'Файл «{version.filename}» отклонён: непредвиденный ответ антивируса', payload={'verdict': verdict},
            correlation_id=job.correlation_id,
        )
        db.commit()
        return {'state': version.state, 'scan_result': version.scan_result}

    documents_dir = Path(settings.documents_dir) / 'documents'
    documents_dir.mkdir(parents=True, exist_ok=True)
    target_path = documents_dir / version.storage_key
    quarantine_path.replace(target_path)  # atomic same-volume move (os.replace under the hood)
    version.scan_result = 'clean'
    version.state = 'linked'  # Validated -> Linked happens in this same job step; see module docstring.
    record_event(
        db, None, user, 'document.linked', entity_type='document_version', entity_id=version.id,
        summary=f'Файл «{version.filename}» проверен и опубликован' + (f' (документ «{document.title}»)' if document else ''),
        payload={'document_id': version.document_id}, correlation_id=job.correlation_id,
    )
    db.commit()
    return {'state': version.state, 'scan_result': version.scan_result}


JOB_HANDLERS['document_scan'] = run_document_scan
