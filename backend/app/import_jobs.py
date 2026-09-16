"""Background-job handlers for the generic entity-import wizard (T-091/T-092).

`app.jobs.enqueue(db, 'import_apply', {...})` is used by `import_routes.py`'s apply endpoint for the three
generic entities (`universities`, `university_contacts`, `interactions`); the existing contract importer
keeps writing synchronously in the request, unchanged (see the report for why). `'import_rollback'` undoes
a previously-applied generic import, skipping rows changed since (the "safe" rollback of
`docs/design/file-ingestion-plan.md` §3.2).
"""
from sqlalchemy import select

from . import entity_import
from .audit import record_event
from .jobs import JOB_HANDLERS
from .models import CatalogImport, User, utcnow


def _load_locked(db, import_id):
    record = db.scalar(select(CatalogImport).where(CatalogImport.id == import_id).with_for_update())
    if record is None:
        raise RuntimeError(f'catalog import {import_id} not found')
    return record


def run_import_apply(db, job):
    payload = job.payload
    import_id = payload['catalog_import_id']
    entity = payload['entity']
    mapping = payload['mapping']
    user_id = payload.get('user_id')

    record = _load_locked(db, import_id)
    if record.status == 'applied':
        # Already applied (e.g. a retried job after a crash right after commit); idempotent no-op.
        return record.report or {}

    user = db.get(User, user_id) if user_id else None
    rows = entity_import.build_rows(record.headers, record.rows, mapping)
    report = entity_import.run_import(db, user, entity, record.headers, mapping, rows, apply=True, correlation_id=job.correlation_id)

    record.status = 'applied'
    record.mapping = mapping
    record.report = report
    record.applied_at = utcnow()
    record_event(
        db, None, user, 'import.apply', entity_type='catalog_import', entity_id=record.id,
        summary=f'Применена загрузка «{record.filename}»: строк {report["summary"]["valid"]} из {report["summary"]["rows"]}',
        payload={'filename': record.filename, 'entity': entity, 'summary': report['summary']},
        correlation_id=job.correlation_id,
    )
    db.commit()
    return report


def run_import_rollback(db, job):
    payload = job.payload
    import_id = payload['catalog_import_id']
    user_id = payload.get('user_id')

    record = _load_locked(db, import_id)
    entity = entity_import.decode_entity(record)
    if entity == 'contracts':
        raise RuntimeError('Откат не поддерживается для импорта договоров')
    if record.status != 'applied':
        raise RuntimeError('Эта загрузка ещё не применена')

    rollback_entries = (record.report or {}).get('rollback') or []
    # The lock is released for the duration of rollback_import's own per-row commits (see its docstring);
    # re-fetch afterwards to attach the final report to the current state of the row.
    db.commit()
    items = entity_import.rollback_import(db, rollback_entries)
    summary = {
        'total': len(items),
        'rolled_back': sum(1 for item in items if item['status'] == 'rolled_back'),
        'not_rolled_back': sum(1 for item in items if item['status'] == 'not_rolled_back'),
    }
    result = {'summary': summary, 'items': items}

    record = db.get(CatalogImport, import_id)
    user = db.get(User, user_id) if user_id else None
    record.report = {**(record.report or {}), 'rollback_result': result}
    record_event(
        db, None, user, 'import.rollback', entity_type='catalog_import', entity_id=record.id,
        summary=f'Откат загрузки «{record.filename}»: отменено {summary["rolled_back"]} из {summary["total"]}',
        payload=summary, correlation_id=job.correlation_id,
    )
    db.commit()
    return result


JOB_HANDLERS['import_apply'] = run_import_apply
JOB_HANDLERS['import_rollback'] = run_import_rollback
