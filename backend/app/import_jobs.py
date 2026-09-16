"""Background-job handlers for the generic entity-import wizard (T-091/T-092).

Placeholder: registers no handlers yet. `app.jobs.enqueue(db, 'import_apply', {...})` will fail with "no
handler registered" until this module adds `JOB_HANDLERS['import_apply'] = run_import_apply` (and
`'import_rollback'` for T-092). Importing this module must stay side-effect-free beyond that registration —
`worker.py` imports it unconditionally at startup.
"""
from .jobs import JOB_HANDLERS  # noqa: F401
