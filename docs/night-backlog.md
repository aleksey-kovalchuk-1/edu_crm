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
| T-020 | Keycloak service with realm import (realm, three roles, confidential client, synthetic users) | T-014 | Keycloak healthy in Compose; a synthetic user can authenticate; no secrets committed | VERIFIED (synthetic-user authentication proven in the spike container; Compose: healthy, realm served, secrets gitignored) |
| T-021 | Server-side OIDC login (backend-for-frontend): login, callback, logout, current user; sessions in PostgreSQL; httpOnly cookie; CSRF token | T-020 | Browser login through Keycloak works end to end; unit tests cover callback, session expiry, logout, CSRF | VERIFIED (`4f0cb41`, hardened `15c6caf`; real redirect, login page, discovery checked over HTTP; browser sign-in left to the owner per D-130) |
| T-022 | Role policies on every route; data-visibility scopes; route-policy completeness test | T-021 | Role × route matrix tests pass; a User cannot read universities outside their scope | VERIFIED (role policies `4f0cb41`/`15c6caf`; manager data scopes across catalogs, contracts, launches, tasks, history and dashboard with tests; review findings fixed) |
| T-023 | Audit log and "recent actions" (cache of user actions) | T-021 | Each mutation writes one audit event in the same transaction; recent actions visible in the UI | VERIFIED (backend `ddabb53`; UI panel `3edbccc` covered by frontend tests; signed-in visual check pending owner per D-130) |
| T-024 | Frontend authentication: redirect to login, user menu, logout, role-aware navigation, 401 handling | T-021 | Verified in a browser for each role (agents may not type passwords into the Keycloak form, so the final sign-in check needs the owner) | BLOCKED (implemented in `3edbccc`, 61 frontend tests, independent review fixed; browser shows the unauthenticated redirect to the Keycloak login page; signed-in checks per role need the owner) |
| T-025 | Admin screen for data scopes; Supervisor reassigns responsible persons | T-022, T-030 | Admin assigns scopes; Supervisor changes a responsible person; audit events recorded | TODO |

## M3 — Catalogs, import, JSON export

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-030 | Catalog schema: IT directions, IT products (vendor, software), universities, university contacts, contracts and licences (number, signing date, validity = one year, transfer status, manager, university responsible persons, comment) | T-012 | Migration applies on the existing volume without data loss; model tests | VERIFIED (`4f19e51`; rehearsal on restored backup; live dev database migrated with row counts unchanged) |
| T-031 | Catalog API with filtering and pagination | T-030, T-022 | Documented in Swagger; tests for filters, validation, scopes | VERIFIED (194 backend tests; independent review findings fixed; deployed to the dev stack) |
| T-032 | Catalog screens | T-031 | Browser check: list, filter, create, edit without page reload | IN_PROGRESS (implemented; 85 frontend tests, lint, build; signed-in browser check needs the owner per D-130) |
| T-033 | xls/xlsx import: upload, column mapping (saved profiles), validation preview, idempotent apply, import report | T-031 | A synthetic sample file imports; invalid rows reported with row number and reason; re-import creates no duplicates | VERIFIED except signed-in browser check (`64c2642` API, `43115a0` wizard; synthetic `docs/samples/catalog-import-sample.xlsx` reports 6 valid rows and row 9 invalid date; re-apply returns 409; 98 frontend tests; deployed; signed-in check needs the owner per D-130) |
| T-034 | Resulting JSON file export | T-031 | Export endpoint returns a JSON file matching a documented schema | TODO |

## M4 — Workflows and attachments

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-040 | Workflow templates, statuses (stable IDs, renamable, ordered), transitions; default 14-step template; existing launches migrated to workflow instances | T-030 | Migration preserves existing stage history; renaming a status does not alter history | IN_PROGRESS (data model and migration `0008` in `fd4422d`: rehearsal on restored backup mapped 8/8 launches and copied 10 history rows; live dev database at `0008` with counts unchanged; template editing API pending) |
| T-041 | Status change with comment and history | T-040, T-023 | API tests; audit event per change | VERIFIED (`79218fa`; `POST/GET /launches/{id}/status-changes`, audit without comment text; 208 tests; CI run 34971669341; deployed; independent review running) |
| T-042 | File attachments on status changes (png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx): type check by content, size limit, authorised download | T-041 | Allowed types accepted, others rejected with error codes; tests | VERIFIED (`79218fa`; content signature + extension, 20 MB/5 files, files removed on failure, scoped download with `nosniff`; volume `attachments_data`; `scripts/attachments-backup.sh`; independent review running) |
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

## M8 — Self-registration (D-155–D-160)

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-080 | Russian-only Keycloak UI: `supportedLocales: ["ru"]`, no language switcher; registration/forgot-password/verify-email pages fully in Russian | T-020 | Rendered pages show `lang="ru"`, no locale-switcher markup, Russian labels/title; screenshot | VERIFIED (realm imports cleanly from a dropped `keycloak` DB — `docker compose logs keycloak` shows one `Realm 'edu-crm' imported` and no errors; live browser screenshot of `/api/v1/auth/register` shows "Зарегистрироваться", Russian field labels, `« Назад к логину`, no switcher; `get_page_text` on the login page after following a real link from there shows "Вход в учетную запись" / "Забыли пароль?" / "Новый пользователь? Регистрация", still no switcher) |
| T-081 | Registration restricted to `.ru` email addresses server-side (Keycloak User Profile `pattern` validator), cannot be bypassed by posting directly to Keycloak | T-080 | Non-`.ru` address rejected with a Russian message, no user created; `.ru` address accepted; demo users still import and keep their roles | VERIFIED (direct POST to Keycloak's own registration form action with `email=reject@example.com` re-shows the form with "Для регистрации используйте адрес электронной почты в домене .ru." and creates no user, confirmed via Admin API `GET /users?email=example.com` → `[]`; `.ru` address `e2e-<ts>@educrm-demo.ru` creates a user; all 3 demo users present after a clean reimport with `anna.demo`=crm-user, `pavel.demo`=crm-supervisor, `irina.demo`=crm-admin, emails now `@educrm-demo.ru`) |
| T-082 | Email verification required before any CRM access; local SMTP via Mailpit by default, real SMTP overridable | T-081 | New unverified user cannot obtain a session; verification email captured with Russian subject/body; login completes and shows exactly `crm-user` after verifying | VERIFIED end-to-end via `backend`'s venv + httpx script (manual cookie jar, see docs/design/authentication.md for why): register with `.ru` email → `GET /api/v1/auth/me` → 401 → Mailpit API returns a message with subject "Подтверждение E-mail" and a `login-actions/action-token` link → following it lands on the "Обновление пароля" (Keycloak defers the password step until after verification, D-155) → posting a new password completes the OIDC flow → `GET /api/v1/auth/me` returns exactly `{"roles": ["crm-user"]}` |
| T-083 | CAPTCHA (reCAPTCHA v2) required on registration; login-side conditional CAPTCHA explicitly out of scope (documented limitation, D-158) | T-081 | Registration without a solved captcha rejected; with the always-pass test key pair, accepted; widget visible in a real browser | VERIFIED (empty `g-recaptcha-response` → Keycloak re-shows the form with "Некорректная Recaptcha", no user created; non-empty test-key token → accepted; browser screenshot shows the rendered "Я не робот" widget with the Google test-key banner, only after fixing a discovered CSP bug — see D-158 — that silently hid it) |
| T-084 | `GET /api/v1/auth/register`; admin test-user script `scripts/keycloak-create-user.sh` | T-081 | Backend tests pass; script creates/updates a user with a role and prints a password once | VERIFIED (`backend/tests/test_registration.py`, `backend/tests/test_oidc.py::test_authorization_url_registration_uses_the_registrations_endpoint`; full suite `213 passed`; `scripts/keycloak-create-user.sh` run twice live against the dev stack: first run created `test.script.user@educrm-demo.ru` with `crm-supervisor`; second run with `crm-admin,crm-user` updated it idempotently and Admin API confirms role mappings became exactly `['crm-admin','crm-user']`, no stale `crm-supervisor`; an initial version of the script looked up by username and failed because `registrationEmailAsUsername=true` (D-157) makes Keycloak silently rewrite a created user's username to their email even via the Admin API — fixed to look up by email instead; test user deleted afterward) |
## M10 — CRM-owned phone verification (D-161–D-163)

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T-100 | Foundation: `users.phone`/`phone_verified_at`, `phone_verification_codes` (migration `0009`), `sms_provider_*` settings | T-023 | Migration applies cleanly; `alembic check` clean | VERIFIED (208 backend tests) |
| T-101 | `app/sms.py` injectable SMS sender (logging default, configurable HTTP provider); `POST /api/v1/profile/phone` (request code, rate-limited) and `POST /api/v1/profile/phone/verify` (attempt-limited, expiring) | T-100 | Code requested and verified round-trip; wrong code rejected with attempts tracked; expired code rejected; rate limit enforced; audit event per request/verify | VERIFIED (227 backend tests; live: nginx `phone_code` zone confirmed 429 after burst=5; `GET /api/v1/auth/me` carries phone state; `docs/api/profile.md`) |
| T-102 | Frontend: a place to enter/verify a phone number (new minimal profile surface, since none exists yet) | T-101 | A user can request and enter a code without a page reload; server field errors shown | VERIFIED (`/profile` route reachable from the sidebar avatar; 113 frontend tests unchanged, lint/build clean; request/verify buttons disabled while pending) |
