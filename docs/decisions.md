# Decisions and Assumptions

Sources of authority, highest first: owner decisions → `docs/specification.md` → technical decisions below. Earlier AI-generated plans are not requirements.

Status values: `OWNER` (explicit owner decision), `ASSUMED` (default the owner may override), `PROPOSAL` (needs owner approval before implementation).

## Owner decisions

| ID | Decision | Status |
|---|---|---|
| D-001 | Stack: React, TypeScript, FastAPI, PostgreSQL, Docker | OWNER |
| D-002 | Authentication through Keycloak; no custom password authentication | OWNER |
| D-003 | No external university portal at this stage | OWNER |
| D-004 | Do not remove existing modules (tasks, Superset) because earlier reports suggested it | OWNER |
| D-005 | Work on an `ai/` branch; push the branch and draft PRs allowed; never merge to `main` | OWNER |
| D-006 | Never delete database volumes; use compatible migrations and backups | OWNER |
| D-007 | Synthetic data only; no personal data or secrets in source control, screenshots, logs, artifacts | OWNER |
| D-008 | Mock LMS and website contracts until real ones are provided, labelled as mocks | OWNER |
| D-009 | Run until 2026-09-16 08:30 MSK within the Pro plan limits; when a command needs approval, continue with other work | OWNER |
| D-010 | Major product changes, architecture replacements, new external services, destructive changes require owner approval | OWNER |

## Technical decisions

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-101 | Roles: `crm-user` (CAM), `crm-supervisor`, `crm-admin` as Keycloak realm roles | Matches the specification's three roles | ASSUMED |
| D-102 | Keycloak holds identity and roles; the CRM database holds data-visibility scopes managed by the Administrator in the CRM | Scope checks stay inside SQL queries | ASSUMED |
| D-103 | Visibility: User sees and edits assigned universities; Supervisor sees all and reassigns responsible persons; Administrator sees all and manages access | Least-privilege default | ASSUMED |
| D-104 | Login is server-side (backend-for-frontend): confidential OIDC client, sessions in PostgreSQL, httpOnly cookie, CSRF token | Tokens never reach browser JavaScript | ASSUMED |
| D-105 | "Cache of user actions" = audit trail of who did what and when, shown as recent actions | Most useful reading of an ambiguous requirement | ASSUMED |
| D-106 | PostgreSQL is the only database, including tests (template database cloned per test) | Migrations must be tested on the production engine | ASSUMED |
| D-107 | Schema changes only through Alembic; existing databases are stamped, never recreated | D-006 | ASSUMED |
| D-108 | Russian ordering through per-column ICU collation (`ru-RU-x-icu`), not by re-initialising the cluster | Verified available in `postgres:16-alpine`; respects D-006 | ASSUMED |
| D-109 | Report jobs use a PostgreSQL-backed queue and a worker container; no Redis | Meets 10 parallel reports without a new service | ASSUMED |
| D-110 | Attachments stored on a Docker volume behind a storage interface; content-based type checks and size limits | No new service; MinIO and antivirus scanning are proposals | ASSUMED |
| D-111 | Legacy `.xls` export by converting xlsx with LibreOffice in the worker image | The specification requires `.xls`; Python `.xls` writers are unmaintained | ASSUMED |
| D-112 | Russian user interface and documentation; English code, comments, commit messages | Target users are Russian-speaking; code stays conventional | ASSUMED |
| D-113 | Python 3.12 in Docker and CI is authoritative; local 3.14 is for convenience | Matches the production image | ASSUMED |
| D-114 | Milestone tags use `ai-mN-<name>-YYYYMMDD` and are never moved | Unique, recoverable versions | ASSUMED |
| D-115 | The lead agent alone owns migrations, the API contract, and Compose/deployment files; subagents get non-overlapping files | Avoids conflicting edits | ASSUMED |
| D-116 | The A1 spec draft (custom session authentication) is superseded by D-002; kept for history | Owner decision overrides it | ASSUMED |
| D-117 | Keycloak `quay.io/keycloak/keycloak:26.7.3`; realm `edu-crm` imported from `deploy/keycloak/realm-edu-crm.json`; client secret and demo passwords substituted from environment variables (`${VAR}`), required in Compose with `${VAR:?}` because an unset variable is imported as literal text | Verified in a throwaway container on 2026-09-15 (see night report) | ASSUMED |
| D-118 | The backend keeps only `crm-*` values from the token `roles` claim; built-in roles (`default-roles-edu-crm`, `offline_access`, `uma_authorization`) are ignored | Tokens carry built-in roles alongside CRM roles | ASSUMED |
| D-120 | Every API error response is `{"code", "message", "details"}` with codes from `backend/app/errors.py`, documented in `docs/api/errors.md`; the frontend shows `message` and the `code` | Specification requires error codes; one shape keeps clients simple | ASSUMED |
| D-121 | Frontend: React Router for pages, TanStack Query for server state with targeted cache invalidation, Vitest + Testing Library + ESLint for checks | Multiple screens and the no-reload / 1-second requirements; current single file refetches everything after each change | ASSUMED |
| D-122 | Keycloak is published through nginx at `/auth` (`KC_HTTP_RELATIVE_PATH=/auth`, `KC_HOSTNAME=http://localhost:8080/auth`, `KC_PROXY_HEADERS=xforwarded`, `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`); the API reaches it at `http://keycloak:8080/auth` | One browser origin and port; stable token issuer | ASSUMED |
| D-123 | Keycloak runs in production mode (`start --import-realm`) with its own PostgreSQL database `keycloak` and role on the existing server, created idempotently by a one-shot init service | Supported, persistent mode; the data volume is not re-initialised | ASSUMED |
| D-124 | OIDC authorization-code flow with PKCE implemented with `httpx` and `PyJWT[crypto]` (JWKS verification); login state stored in PostgreSQL | Few dependencies; any API worker can complete the callback | ASSUMED |
| D-125 | Sessions keep the Keycloak refresh token encrypted (Fernet key from environment) and revalidate with Keycloak at most every 120 s; a failed refresh revokes the CRM session | Disabling a user or ending the Keycloak session stops CRM access within minutes | ASSUMED |
| D-126 | A `users` table mirrors Keycloak identity (`sub`, email, name, cached `crm-*` roles) for assignments and audit; Keycloak stays the source of roles | CRM data (responsible persons, audit) needs stable local user references | ASSUMED |
| D-127 | Russian ordering is implemented as ICU collation `ru-RU-x-icu` on each user-visible text column (migration `0002`) | Implements D-108 on existing databases | ASSUMED |
| D-128 | Universities are catalog data: only `crm-supervisor` and `crm-admin` may create them; all three roles read data, create launches, change stages and tasks until data-visibility scopes are implemented | Catalogs are maintained by heads and administrators; managers work on interactions | ASSUMED |
| D-129 | Local secrets (Keycloak admin, Keycloak database role, client secret, demo passwords, session encryption key) are generated by `scripts/generate-dev-secrets.sh` into gitignored `deploy/local/*.env` files loaded through Compose `env_file`; `.env` holds only non-secret defaults | Nothing secret is committed; setup works without editing `.env` | ASSUMED |
| D-130 | Agents never type passwords into the Keycloak login form; the login flow is verified by tests against a fake identity provider, by HTTP checks of the real redirect, page and discovery, and the final browser sign-in is left to the owner | Safety rule for credentials | OWNER |
| D-131 | Audit trail (D-105): `audit_events` stores actor, action, entity, Russian summary, JSON payload and IP; written in the same transaction as the change; managers see their own recent actions, heads and administrators see everyone's | Least privilege for personal activity data | ASSUMED |
| D-119 | Constraint names follow PostgreSQL defaults (`<table>_pkey`, `<table>_<column>_fkey`, `<table>_<column>_key`) through the SQLAlchemy naming convention | Databases built by `create_all` before migrations keep identical names, so the baseline can be stamped | ASSUMED |

## Proposals awaiting owner approval

| ID | Proposal | Why it is not assumed |
|---|---|---|
| P-001 | MinIO for attachments | New external service (D-010) |
| P-002 | ClamAV scanning of uploads | New external service; about 1–3 GB RAM |
| P-003 | Branch protection on `main` | Repository setting; owner action |
