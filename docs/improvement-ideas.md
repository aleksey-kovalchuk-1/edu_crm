# Improvement Ideas

Candidates found while working. Each records the observed problem, evidence, expected benefit, scope and regression risk, and how success is verified. Items that are already backlog tasks reference the task ID.

Status values: `CANDIDATE`, `SCHEDULED` (moved to the backlog), `DONE`, `DEFERRED`, `REJECTED`.

| ID | Problem | Evidence | Benefit | Scope / risk | Verification | Status |
|---|---|---|---|---|---|---|
| I-001 | `web` container has no healthcheck | `docker compose ps` shows `Up` without `(healthy)` (preflight 2026-09-15) | Compose and operators can detect a broken frontend | Small; Compose only | `docker compose ps` shows `healthy` | SCHEDULED (T-014) |
| I-002 | Swagger UI is not reachable through nginx | `:8080/docs` returns the SPA; `:8080/api/v1/openapi.json` returns 404 | Specification requires methods described in Swagger UI | Small; API docs path and nginx | `curl :8080/api/docs` returns Swagger HTML | SCHEDULED (T-014) |
| I-003 | Every mutation in the UI refetches five endpoints | `mutate()` calls `load()` in `frontend/src/App.tsx` | Faster interactions toward the 1-second requirement | Medium; frontend data layer | Network panel shows one request per change | SCHEDULED (T-043) |
| I-004 | No frontend tests or lint | `frontend/package.json` has only `dev`, `build`, `preview` | Catch UI regressions in CI | Small | `npm test` and lint in CI | SCHEDULED (T-075) |
| I-005 | Deprecation warnings from the test client (`httpx` with Starlette test client, `anyio.abc.BlockingPortal`) | `pytest` output, preflight 2026-09-15 | Avoid future breakage on dependency upgrades | Small; test dependencies | `pytest -W error::DeprecationWarning` passes | CANDIDATE |
| I-006 | Local Python 3.14 differs from Docker/CI 3.12 | `python3 --version` vs `backend/Dockerfile` | Reproducible local checks | Documentation or tooling only | Tests also run inside the API image | CANDIDATE |
| I-007 | Stage stored as an integer position | `backend/app/models.py` `Launch.stage` | Renaming or reordering statuses would corrupt history | Covered by workflow redesign | Migration test preserves history | SCHEDULED (T-040) |
