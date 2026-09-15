# Platform Foundation (Phase 0, Spec A1) — Design

- **Date:** 2026-09-14
- **Status:** SUPERSEDED on 2026-09-15. The official specification (`docs/specification.md`) requires Keycloak, so the custom password and session authentication in sections 4.4–4.6 and 4.9 will not be implemented. Still-valid parts (PostgreSQL only, Alembic, migrations in tests, audit log, Docker entrypoint) continue in `docs/night-backlog.md` and `docs/decisions.md`. Do not implement from this document.
- **Related specs:** A2 — Directory model and universal ingestion (`/sveden/` first connector); B — Frontend restructure

## 1. Context

The project is heading to a pilot with one institution. This phase builds the load-bearing structure that is expensive to retrofit once MVP features and real data exist.

Current state (commit `7cc940e`):

- FastAPI app in a single module (`backend/app/main.py`); five tables created at startup by `Base.metadata.create_all`.
- SQLite is the default database; PostgreSQL is used only in Docker Compose.
- No authentication, roles, or audit trail. The README states that real personal data must not be loaded before authentication, server-side roles, and an action log exist.
- Demo data is seeded inside the application lifespan.
- Docker Compose verified on 2026-09-14: `db` and `api` healthy, `web` up (it has no healthcheck); `/api/v1/health` returns 200 directly and through nginx.

## 2. Goals

1. Schema changes are managed only by Alembic migrations; the application never creates tables.
2. PostgreSQL is the only supported database, with Russian collation.
3. Users authenticate with server-side sessions in httpOnly cookies.
4. Every endpoint has an explicit role policy; unknown users get 401, disallowed roles get 403.
5. Every data mutation and authentication event is recorded in an audit log, atomically with the change.
6. `docker compose up --build` migrates, optionally seeds, and starts a healthy stack with no manual steps.
7. The existing interface keeps working by logging in (minimal compatibility only; full restructure is spec B).

## 3. Non-goals

| Out of scope | Where it goes |
|---|---|
| Router, page split, auth context, protected routes in React | Spec B |
| Campuses, departments, programmes, official identifiers, ingestion | Spec A2 |
| User management API or UI (users are managed by CLI) | MVP |
| Reads scoped to an institution representative's own university | Portal (requirement 5) |
| Login rate limiting and account lockout | Required before any exposure beyond loopback; Phase 5 |
| Database-enforced audit immutability (separate DB role) | Phase 5 |
| Password reset by email, MFA, SSO | Later |
| File storage | Document workstream (requirement 4) |
| Backups | Phase 5 |

This spec provides prerequisites for 152-FZ work (identity, access control, audit). It does not by itself establish compliance.

## 4. Decisions

### 4.1 PostgreSQL only

- Remove the SQLite default URL, the SQLite `connect_args`, and the `PRAGMA foreign_keys` listener from `create_app`.
- `DATABASE_URL` is required. If it is unset, startup fails with a clear message.
- **Why:** migrations use PostgreSQL-specific features (`timestamptz`, `jsonb`, `inet`, ICU collation). Running them on SQLite would fail or produce a different schema — the divergence that running migrations in tests is meant to prevent.
- Local development without Docker for the API still needs PostgreSQL: `docker compose up -d db` and `DATABASE_URL=postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/edu_crm`.

### 4.2 Russian collation (ICU)

- The `db` service sets `POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=ru-RU"`.
- The image stays `postgres:16-alpine`. Verified on 2026-09-14 in a throwaway container: with ICU `ru-RU` as the default, `ORDER BY` yields `Анна, ёж, елка, Жанна, Яков`; the current libc default yields `Анна, Жанна, Яков, елка, ёж`.
- These arguments apply only when a data volume is initialised. Existing volumes must be recreated (section 7).
- The CI PostgreSQL service uses the same arguments.

### 4.3 Migrations (Alembic)

- Files: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/`.
- `env.py` reads `DATABASE_URL`, uses `Base.metadata` as `target_metadata`, and sets `compare_type=True`.
- `Base` gets a deterministic `MetaData(naming_convention=...)` for primary keys, foreign keys, unique, check, and index names, so generated constraint names are stable across environments.
- Revision `0001_baseline` creates the current five tables (`universities`, `launches`, `tasks`, `stage_events`, `annual_metrics`) exactly as the models define them today.
- Revision `0002_identity_audit` creates `users`, `sessions`, and `audit_events` (section 4.4).
- Both revisions implement `downgrade`.
- `Base.metadata.create_all` is removed from the lifespan.
- The API image copies `alembic.ini` and `migrations/`.

### 4.4 Schema: users, sessions, audit events

**`users`**

| Column | Type | Rules |
|---|---|---|
| `id` | integer PK | |
| `email` | varchar(254) | not null, unique; stored lowercase; `CHECK (email = lower(email))` |
| `password_hash` | varchar(255) | not null |
| `full_name` | varchar(200) | not null |
| `role` | varchar(32) | not null; `CHECK (role IN ('admin','manager','analyst','institution_rep'))` |
| `university_id` | integer | null; FK `universities.id` `ON DELETE RESTRICT` |
| `is_active` | boolean | not null, default true |
| `created_at` | timestamptz | not null, default `now()` |

- `CHECK (role <> 'institution_rep' OR university_id IS NOT NULL)`.
- Roles use `varchar` plus `CHECK` rather than a native enum, because PostgreSQL enum values cannot be removed and are awkward to change in migrations.
- Users are never deleted; they are deactivated. This keeps audit references valid.

**`sessions`**

| Column | Type | Rules |
|---|---|---|
| `id` | varchar(64) PK | hex SHA-256 of the raw session token; the raw token is never stored |
| `user_id` | integer | not null; FK `users.id` `ON DELETE RESTRICT`; indexed |
| `csrf_token` | varchar(64) | not null |
| `created_at` | timestamptz | not null, default `now()` |
| `expires_at` | timestamptz | not null |
| `revoked_at` | timestamptz | null |

- Raw tokens come from `secrets.token_urlsafe(32)`.
- A session is valid when `revoked_at IS NULL AND expires_at > now()` and the user is active.

**`audit_events`**

| Column | Type | Rules |
|---|---|---|
| `id` | bigint identity PK | |
| `occurred_at` | timestamptz | not null, default `now()` |
| `user_id` | integer | null (system, CLI, or unauthenticated attempt); FK `users.id` `ON DELETE RESTRICT` |
| `action` | varchar(64) | not null; dot-namespaced, e.g. `launch.stage_change` |
| `entity_type` | varchar(64) | null |
| `entity_id` | varchar(64) | null |
| `payload` | jsonb | not null, default `'{}'` |
| `ip` | inet | null |

- Indexes: `(entity_type, entity_id)` and `(user_id, occurred_at)`.
- Append-only by convention: no code path updates or deletes audit events.
- Payloads never contain passwords, password hashes, session tokens, or CSRF tokens.

### 4.5 Authentication

- Password hashing: `argon2-cffi` `PasswordHasher` with library defaults. After a successful login, if `check_needs_rehash` is true, the hash is updated.
- The CLI enforces a minimum password length of 12 characters.
- Session cookie: name `edu_crm_session`; `HttpOnly`; `SameSite=Lax`; `Path=/`; `Max-Age` equal to the session TTL; `Secure` controlled by `COOKIE_SECURE` (default `true`; Compose sets `false` for `http://localhost`).
- Session lifetime: absolute `SESSION_TTL_HOURS` (default 12). No sliding renewal in this phase.

Endpoints:

| Method and path | Success | Failure |
|---|---|---|
| `POST /api/v1/auth/login` body `{email, password}` | 200 `{user, csrf_token}` and `Set-Cookie` | 401 `{"detail": "Неверный email или пароль"}` |
| `POST /api/v1/auth/logout` | 204; session revoked; cookie cleared | 401 or 403 |
| `GET /api/v1/auth/me` | 200 `{user, csrf_token}` | 401 |

- Login returns the same 401 body for an unknown email, a wrong password, and an inactive user. For an unknown email it still verifies against a fixed dummy hash so response time does not reveal whether the account exists.
- `GET /auth/me` returns the CSRF token so the single-page app can recover it after a reload. Other sites cannot read that response because the API sends no CORS headers.
- `user` is the `UserPublic` schema: `id`, `email`, `full_name`, `role`, `university_id`, `is_active`.
- **`serialize()` must never be used for `User`.** It returns every column, including `password_hash`. Users are always returned through `UserPublic`.
- Deactivating a user or changing their password revokes all of their sessions.

### 4.6 CSRF protection

- Every `POST`, `PUT`, `PATCH`, and `DELETE` under `/api/v1`, except `POST /auth/login`, requires an `X-CSRF-Token` header equal to the session's `csrf_token` (constant-time comparison). Otherwise: 403.
- For every unsafe method, including login: if an `Origin` header is present, it must be in `ALLOWED_ORIGINS`. Otherwise: 403.
- `SameSite=Lax` is the baseline; the token and origin check are defence in depth.

### 4.7 Authorization (roles)

- A dependency factory `require_roles(*roles)` resolves the current user and enforces the role. Not authenticated: 401. Authenticated with a disallowed role: 403.

| Route | Public | admin | manager | analyst | institution_rep |
|---|---|---|---|---|---|
| `GET /api/v1/health` | yes | | | | |
| `POST /api/v1/auth/login` | yes | | | | |
| `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` | | yes | yes | yes | yes |
| `GET /stages`, `/universities`, `/launches`, `/launches/{id}/history`, `/tasks`, `/dashboard` | | yes | yes | yes | **403** |
| `POST /universities`, `POST /launches`, `PATCH /launches/{id}`, `PATCH /tasks/{id}` | | yes | yes | 403 | 403 |

- Institution representatives are denied all current reads. Without scoped queries, a representative could otherwise read every university's data. Scoped reads arrive with the portal.
- `/api/v1/health` stays public: the Compose healthcheck calls it, and `web` waits for `api` to be healthy.
- In this phase `admin` has the same data rights as `manager`; user administration is CLI-only.
- A test fails if any route has no explicit policy (section 6).

### 4.8 Audit logging

- Helper: `audit(db, *, actor, action, entity_type=None, entity_id=None, payload=None, request=None)` adds an `AuditEvent` to the current session without committing.
- Mutation handlers call it before `db.commit()`, so the change and its audit event commit together or not at all.
- A failed login is recorded and committed in its own transaction before the 401 is returned.

| Action | Trigger | `user_id` | Payload |
|---|---|---|---|
| `auth.login.success` | successful login | the user | `{}` |
| `auth.login.failure` | failed login | the account if it exists, else null | `{"email": <normalised email>}` |
| `auth.logout` | logout | the user | `{}` |
| `university.create` | `POST /universities` | actor | `{"name", "city"}` |
| `launch.create` | `POST /launches` | actor | `{"university_id", "program", "stage": 0}` |
| `launch.stage_change` | `PATCH /launches/{id}` when the stage changes | actor | `{"from", "to"}` |
| `task.update` | `PATCH /tasks/{id}` when `done` changes | actor | `{"done": {"from", "to"}}` |
| `user.create`, `user.deactivate`, `user.set_password` | CLI | null | `{"email", "role"}` |

- A request that changes nothing (same stage, same `done` value) writes no audit event and still returns 200.
- IP address: `request.client.host`, with uvicorn running `--proxy-headers`. nginx overwrites `X-Forwarded-For` with `$remote_addr` instead of appending to it, and sets `X-Forwarded-Proto`.

### 4.9 Bootstrap and seeding

- New module `backend/app/cli.py`, run as `python -m app.cli <command>`:
  - `create-user --email --full-name --role [--university-id]` — password from an interactive prompt, or from `EDU_CRM_PASSWORD` for non-interactive use; never from command-line arguments.
  - `set-password --email` — revokes the user's sessions.
  - `deactivate-user --email` — revokes the user's sessions.
  - `seed-demo` — runs the existing demo seed if there are no universities, and creates four demo users if there are no users: `admin@demo.local`, `manager@demo.local`, `analyst@demo.local`, and `rep@demo.local` (linked to the first university). Their password comes from `DEMO_PASSWORD`, which is required for this command.
- The application lifespan no longer seeds, and `create_app` no longer takes `seed_demo`.
- This removes the README caveat about running a single API process during initial seeding.

### 4.10 Docker

- `backend/docker-entrypoint.sh`:
  1. `alembic upgrade head`
  2. if `SEED_DEMO=true`: `python -m app.cli seed-demo`
  3. `exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"`
- API Dockerfile: copy `alembic.ini`, `migrations/`, and the entrypoint; use it as `ENTRYPOINT`.
- `compose.yaml`:
  - `db`: ICU `POSTGRES_INITDB_ARGS`; port `127.0.0.1:5432:5432`; `restart: unless-stopped`.
  - `api`: `COOKIE_SECURE=false`, `SESSION_TTL_HOURS`, `DEMO_PASSWORD`, `ALLOWED_ORIGINS`, `FORWARDED_ALLOW_IPS='*'`; healthcheck `start_period` long enough for migrations; `restart: unless-stopped`.
  - `web`: healthcheck `wget -qO- http://127.0.0.1/ >/dev/null` (`wget` verified present in `nginx:1.28-alpine`); `restart: unless-stopped`.
- `frontend/nginx.conf`: `proxy_set_header X-Forwarded-For $remote_addr;` and `proxy_set_header X-Forwarded-Proto $scheme;`.
- Superset: `superset/readonly.sql` keeps granting only on `analytics_annual`. The BI role must never receive grants on `users`, `sessions`, or `audit_events`, and no `GRANT SELECT ON ALL TABLES` may be added. Its comment changes from "after the API has initialized its tables" to "after migrations have run".

### 4.11 Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | none (required) | SQLAlchemy URL |
| `SESSION_TTL_HOURS` | `12` | absolute session lifetime |
| `COOKIE_SECURE` | `true` | `Secure` cookie attribute; Compose sets `false` |
| `ALLOWED_ORIGINS` | `http://localhost:8080,http://localhost:5173` | origin check for unsafe methods |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | uvicorn trusted proxy addresses; Compose sets `*` |
| `SEED_DEMO` | `false` | entrypoint runs `seed-demo` |
| `DEMO_PASSWORD` | none | password for demo users; required when seeding |
| `TEST_DATABASE_URL` | none | PostgreSQL server URL used by tests |

`.env.example` gains `DEMO_PASSWORD`, `COOKIE_SECURE`, and `SESSION_TTL_HOURS`.

### 4.12 Dependencies

- Add `alembic` and `argon2-cffi` to `backend/requirements.txt`.
- Pin them and their new transitive dependencies (`Mako`, `MarkupSafe`, `argon2-cffi-bindings`, `cffi`, `pycparser`) in `backend/constraints.txt`.

### 4.13 Minimal frontend compatibility

Without this, every data request from the current interface returns 401 once this spec lands. The following is included so `main` keeps a working preview; everything else is spec B.

- `frontend/src/api.ts`: send same-origin cookies; attach `X-CSRF-Token` to unsafe methods; on 401, signal the app to show the login form.
- A login form rendered by `App.tsx` when `GET /auth/me` returns 401; a logout button in the existing top bar.
- No router, no page split, no role-based UI in this spec.

### 4.14 Code layout

```text
backend/
  alembic.ini
  docker-entrypoint.sh
  migrations/
    env.py
    versions/0001_baseline.py
    versions/0002_identity_audit.py
  app/
    main.py        create_app, existing routes, auth routes, dependencies
    models.py      + naming convention, User, Session, AuditEvent
    schemas.py     + LoginInput, UserPublic
    settings.py    environment parsing and validation
    security.py    password hashing, token hashing, CSRF and origin checks
    audit.py       audit() helper
    cli.py         create-user, set-password, deactivate-user, seed-demo
    seed.py        existing demo data
  tests/
    conftest.py    PostgreSQL template database, per-role clients
    test_api.py    existing tests, adapted to an authenticated manager
    test_auth.py
    test_csrf.py
    test_rbac.py
    test_audit.py
    test_migrations.py
```

## 5. Data flow: authenticated mutation

1. The browser sends `PATCH /api/v1/launches/7` with the `edu_crm_session` cookie and `X-CSRF-Token`.
2. The origin and CSRF checks pass, or the request gets 403.
3. `require_roles("admin", "manager")` resolves the session and user, or returns 401 or 403.
4. The handler validates the body (422 on invalid input), loads the launch (404 if missing), and applies the change.
5. If the stage changed, the handler adds the `StageEvent` and calls `audit(...)`.
6. One `db.commit()` persists the change, the stage history, and the audit event together.

## 6. Testing strategy

- `TEST_DATABASE_URL` points at a PostgreSQL server, e.g. `postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/postgres`.
- Session fixture: recreate `edu_crm_test_template` and run `alembic upgrade head` against it once.
- Per test: `CREATE DATABASE edu_crm_test_<random> TEMPLATE edu_crm_test_template`; build the app against it; after the test, dispose the engine and `DROP DATABASE ... WITH (FORCE)`.
- Fixture `client_as(role)`: creates a user, logs in, and returns a client that sends the cookie and CSRF header.

| Area | Tests |
|---|---|
| Migrations | upgrade from empty; downgrade to base then upgrade again; `alembic check` reports no drift between models and migrations; Russian sort order matches section 4.2 |
| Authentication | successful login sets an `HttpOnly`, `SameSite=Lax` cookie; unknown email, wrong password, and inactive user return identical 401 bodies; a cookie is rejected after logout, after expiry, and after deactivation |
| CSRF | a mutation without the header or with a wrong token gets 403; a disallowed `Origin` gets 403 |
| Roles | every route × every role, plus unauthenticated, matches the table in 4.7 |
| Route policy | fails if any route lacks an explicit policy; only `/health` and `/auth/login` may be public |
| Audit | each mutation writes exactly one event with actor, action, entity, and payload; a no-change request writes none; a request failing validation writes none; a failed login is persisted |
| Leak guard | no response body from any tested endpoint contains `password_hash` or `$argon2` |
| Existing | the three current tests pass with an authenticated manager |

CI: the `api` job adds a `postgres:16-alpine` service with the ICU `POSTGRES_INITDB_ARGS` and a `pg_isready` health option, and sets `TEST_DATABASE_URL`.

## 7. Rollout for existing environments

1. `docker compose down -v` — deletes the current volume. Required for ICU collation and for a clean baseline migration. It contains only fictional demo data.
2. Add `DEMO_PASSWORD` (and review the other new variables) in `.env`.
3. `docker compose up --build -d` — the entrypoint migrates and seeds.
4. Open `http://localhost:8080` and log in as a demo user.
5. The README's Docker, local development, and checks sections are updated to match.

## 8. Risks and known limitations

| Risk | Mitigation in this phase |
|---|---|
| No login rate limiting | Ports stay bound to `127.0.0.1`; rate limiting is required before any wider exposure |
| Audit log is append-only only by convention | No update or delete code path; database-level enforcement in Phase 5 |
| A local process calling `127.0.0.1:8000` directly can set its own `X-Forwarded-For` | Documented; requests through nginx record the real address |
| Login CSRF | Mitigated by the origin check when `Origin` is present |
| One-time volume reset | Only fictional data exists today |
| Absolute 12-hour sessions end mid-task | Acceptable for the pilot; sliding renewal can be added later without schema changes |

## 9. Acceptance criteria

- [ ] `create_all` no longer appears in application code; `alembic upgrade head` on an empty database produces the full schema.
- [ ] `alembic check` reports no differences.
- [ ] The application refuses to start without `DATABASE_URL`.
- [ ] A fresh `docker compose up --build -d` brings `db`, `api`, and `web` to healthy with no manual steps.
- [ ] Demo users can log in through `http://localhost:8080`; unauthenticated API reads return 401.
- [ ] The role matrix in 4.7 is enforced and covered by tests.
- [ ] Every mutation writes exactly one audit event in the same transaction.
- [ ] No endpoint response contains a password hash.
- [ ] CI runs the backend tests against PostgreSQL with ICU collation, and the frontend build still passes.
