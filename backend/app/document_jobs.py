"""Background-job handlers for the document quarantine/scan pipeline (T-093).

Placeholder: registers no handlers yet. Add `JOB_HANDLERS['document_scan'] = run_document_scan` (calling
ClamAV via `clamd`, settings.clamav_host/clamav_port) when T-093 lands. Importing this module must stay
side-effect-free beyond that registration -- `worker.py` imports it unconditionally at startup.
"""
from .jobs import JOB_HANDLERS  # noqa: F401
