# Night Backlog

Run window: 2026-09-15 10:57 MSK → 2026-09-16 08:30 MSK. Branch: `ai/crm-foundation`.

Status values: `TODO`, `IN_PROGRESS`, `VERIFIED`, `BLOCKED`. A task is `VERIFIED` only when its acceptance criteria were checked and the evidence is recorded in `docs/night-report.md`.

Priority order: owner decisions and the official specification (`docs/specification.md`) first, then improvements (`docs/improvement-ideas.md`).

## M0 — Setup and safety

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-001 | Working branch, saved specification, tracking documents, supersede the A1 draft | — | Files committed on `ai/crm-foundation` | VERIFIED (`7381a60`) |
| T-002 | Database backup and restore scripts with documentation | — | Backup of the dev volume created; restore into a separate check database reproduces row counts; the restore script refuses to overwrite an existing database | VERIFIED |

## M1 — Foundation

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-010 | Settings module; PostgreSQL only (`DATABASE_URL` required) | T-001 | App fails fast with a clear message without `DATABASE_URL`; no SQLite code paths remain | VERIFIED (`443b8d8`) |
| T-011 | Tests run on PostgreSQL (migrated template database, one clone per test); CI PostgreSQL service | T-010 | `pytest` passes locally against PostgreSQL; CI green | VERIFIED (`443b8d8`, CI run 34902955520) |
| T-012 | Alembic baseline of the current schema; naming convention; `create_all` removed; existing databases stamped automatically | T-011, T-002 | Fresh database reaches the full schema via `alembic upgrade head`; existing dev volume is stamped with row counts unchanged; `alembic check` test passes | VERIFIED (`b90d7ff`) |
| T-013 | Error-code catalogue and JSON error handlers; frontend shows the code | T-010 | 401/403/404/409/422/500 responses carry documented codes; tests cover each | VERIFIED (`b8611f6`) |
| T-014 | Docker: entrypoint (migrate → optional seed → multi-worker server), `web` healthcheck, Swagger reachable through nginx, forwarded-IP headers | T-012 | `docker compose up --build -d` → every service healthy; Swagger UI returns 200 on port 8080 | VERIFIED (`c2c1366`, `a5ba27d`) |
| T-015 | Russian collation for name columns (per-column ICU, no volume recreation) | T-012 | Ordering test returns `Анна, ёж, елка, Жанна, Яков` | VERIFIED (`6ed8c10`) |
| T-016 | Frontend restructure: routed pages, TanStack Query with targeted invalidation and optimistic updates, typed error handling, Vitest and ESLint | T-013 | Independent review findings fixed; `npm run lint`, `npm test`, `npm run build` pass; browser check of routes and a no-reload task toggle in the Compose stack | VERIFIED (`c598b7f`, CI steps `5ff2050`) |

## M2 — Keycloak, roles, audit

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-020 | Keycloak service with realm import (realm, three roles, confidential client, synthetic users) | T-014 | Keycloak healthy in Compose; a synthetic user can authenticate; no secrets committed | TODO |
| T-021 | Server-side OIDC login (backend-for-frontend): login, callback, logout, current user; sessions in PostgreSQL; httpOnly cookie; CSRF token | T-020 | Browser login through Keycloak works end to end; unit tests cover callback, session expiry, logout, CSRF | IN_PROGRESS |
| T-022 | Role policies on every route; data-visibility scopes; route-policy completeness test | T-021 | Role × route matrix tests pass; a User cannot read universities outside their scope | TODO |
| T-023 | Audit log and "recent actions" (cache of user actions) | T-021 | Each mutation writes one audit event in the same transaction; recent actions visible in the UI | TODO |
| T-024 | Frontend authentication: redirect to login, user menu, logout, role-aware navigation, 401 handling | T-021 | Verified in a browser for each role | TODO |
| T-025 | Admin screen for data scopes; Supervisor reassigns responsible persons | T-022, T-030 | Admin assigns scopes; Supervisor changes a responsible person; audit events recorded | TODO |

## M3 — Catalogs, import, JSON export

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-030 | Catalog schema: IT directions, IT products (vendor, software), universities, university contacts, contracts and licences (number, signing date, validity = one year, transfer status, manager, university responsible persons, comment) | T-012 | Migration applies on the existing volume without data loss; model tests | TODO |
| T-031 | Catalog API with filtering and pagination | T-030, T-022 | Documented in Swagger; tests for filters, validation, scopes | TODO |
| T-032 | Catalog screens | T-031 | Browser check: list, filter, create, edit without page reload | TODO |
| T-033 | xls/xlsx import: upload, column mapping (saved profiles), validation preview, idempotent apply, import report | T-031 | A synthetic sample file imports; invalid rows reported with row number and reason; re-import creates no duplicates | TODO |
| T-034 | Resulting JSON file export | T-031 | Export endpoint returns a JSON file matching a documented schema | TODO |

## M4 — Workflows and attachments

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-040 | Workflow templates, statuses (stable IDs, renamable, ordered), transitions; default 14-step template; existing launches migrated to workflow instances | T-030 | Migration preserves existing stage history; renaming a status does not alter history | TODO |
| T-041 | Status change with comment and history | T-040, T-023 | API tests; audit event per change | TODO |
| T-042 | File attachments on status changes (png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx): type check by content, size limit, authorised download | T-041 | Allowed types accepted, others rejected with error codes; tests | TODO |
| T-043 | Workflow screens: board, interaction timeline, status change dialog with comment and files, workflow editor; no page reload | T-041, T-042 | Browser check; status change round trip under 1 s locally (measured) | TODO |
| T-044 | Existing tasks module preserved and linked to interactions | T-040 | Existing task tests pass; tasks visible on the interaction | TODO |

## M5 — Reports and charts

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-050 | Report query with filters (period, universities, IT directions, IT products, responsible, status) and selectable columns | T-040 | Tests compare report rows with fixture expectations | TODO |
| T-051 | Asynchronous report jobs (PostgreSQL queue, worker container) | T-050 | 10 simultaneous report jobs complete; job status visible | TODO |
| T-052 | Report files: xlsx, pdf (Cyrillic), xls | T-051 | Files open and contain the selected columns; tests inspect generated files | TODO |
| T-053 | Charts with PNG and PDF export; statistics of applications, students, streams | T-050 | Exported chart values match API data | TODO |
| T-054 | Reports screen | T-051, T-052 | Browser check: build and download each format | TODO |

## M6 — Integrations

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-060 | Connector framework; documented **mock** LMS and Laravel site APIs; JSON ingestion into new or existing workflows; idempotency | T-041 | Mock payloads create and update workflows; re-run creates no duplicates; documentation states the contracts are mocks | TODO |

## M7 — Quality, security, documentation, delivery

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-070 | Security hardening: headers and CSP, login rate limiting, audit immutability, dependency audit, threat model and measures mapping (no compliance claims) | T-023 | Checks recorded; document maps each measure to code | TODO |
| T-071 | Load test: 50 concurrent users and 10 parallel reports | T-054 | Stored results with percentiles; no claim beyond measured numbers | TODO |
| T-072 | In-app user and admin guides with screenshots of synthetic data | T-043, T-054 | Guides reachable in the UI; screenshots contain no personal data | TODO |
| T-073 | Architecture in Archi, list of libraries, installation guide, data processing and restrictions documents | T-060 | Files present; install guide verified on a clean checkout | TODO |
| T-074 | Superset profile kept working with the new schema (read-only views only) | T-050 | Profile starts; BI role reads only analytics views | TODO |
| T-075 | Frontend tests and lint | T-024 | `npm test` and lint run in CI | TODO |
| T-076 | Mobile layout and accessibility audit (contrast, keyboard, labels) | T-043 | Findings fixed or recorded | TODO |
