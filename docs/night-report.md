# Night Report

- **Run window:** 2026-09-15 10:57 MSK → 2026-09-16 08:30 MSK
- **Branch:** `ai/crm-foundation` (from `main` at `7cc940e`)
- **Backlog:** `docs/night-backlog.md` · **Decisions:** `docs/decisions.md` · **Ideas:** `docs/improvement-ideas.md`

## Current state

Run started. No milestone verified yet.

## Preflight evidence (2026-09-15)

| Check | Result |
|---|---|
| Repository | `main` at `7cc940e`, in sync with origin; CI green on both commits; no other branches, worktrees, stashes, tags, PRs, or active sessions |
| Backend tests | `python -m pytest -q` → 3 passed, 2 deprecation warnings (Python 3.14.5 locally) |
| Frontend | `npm run build` → typecheck and Vite build pass (Node 24.21.0) |
| Docker | Engine 29.8.0, Compose 5.5.1; `db` and `api` healthy, `web` up without healthcheck |
| Swagger | `:8000/docs` 200; not reachable through nginx on `:8080` |
| Keycloak image | `quay.io/keycloak/keycloak:latest` manifest reachable |
| GitHub | `aleksey-kovalchuk-1` has admin rights on the public repository; `main` is not protected |
| Permissions | `.claude/settings.local.json`: `git push` requires approval; `rm -rf` denied |

## Data safety

| Time (UTC) | Action | Evidence |
|---|---|---|
| 2026-09-15 07:57 | `pg_dump -Fc` of the dev database before any schema work | `/Users/alex/dev/edu-crm-backups/edu_crm-20260915T075739Z-pre-foundation.dump` (13,251 bytes; `pg_restore --list` shows 5 table-data entries) |
| 2026-09-15 08:02 | T-002 verification with `scripts/db-backup.sh` / `db-restore.sh` / `db-row-counts.sh` | Restored `edu_crm-20260915T080214Z-t002-check.dump` into `edu_crm_restore_check`: counts identical (annual_metrics 3, launches 8, stage_events 8, tasks 8, universities 6); restore into existing name and into `edu_crm` refused (exit 1); invalid name refused (exit 2); check database dropped; live counts unchanged |

| 2026-09-15 08:09 | Migration rehearsal on a restored copy of the live backup (`edu_crm_stamp_check`) | `python -m app.db_migrate` stamped `0001`; `alembic check` → "No new upgrade operations detected"; row counts identical; check database dropped |
| 2026-09-15 08:11 | Backup `edu_crm-20260915T081100Z-before-alembic-baseline.dump`, then API rebuilt; entrypoint migrated the live dev database | `alembic_version` = `0001`; live row counts unchanged; after `docker compose restart api` the container log shows exactly one `Running stamp_revision` across three migration runs (idempotent); API healthy; `:8080/api/v1/launches` 200 |

## Verification evidence

| Task | Command / check | Result |
|---|---|---|
| T-010, T-011 | `python -m pytest -q` against Compose PostgreSQL | 9 passed |
| T-010, T-011 | Recreated only the `db` container to publish `127.0.0.1:5432` | Row counts unchanged; `db` healthy |
| T-011 | GitHub Actions on `ai/crm-foundation` | Run 34902955520 success (28 s) |
| T-012 | `python -m pytest -q` (adds migrated template, `alembic check`, downgrade/upgrade, pre-migration database adoption) | 13 passed |
| T-012 | GitHub Actions on `b90d7ff` | Run 34933496207 success (37 s) |
| T-013 | `python -m pytest -q` (error shape for 400/401/403/404/405/409/413/415/422/429/500/503, custom messages and headers, hidden internals, documented codes) | 43 passed |
| T-013 | GitHub Actions on `b8611f6` | Run 34933768428 success (36 s) |
| T-014 | `python -m pytest -q` (seeding outside the app, idempotent seed, Swagger under `/api`) | 45 passed |
| T-014 | Backup `edu_crm-20260915T154157Z-before-t014-workers.dump`; `docker compose up -d --build api` | API healthy with uvicorn parent process and workers; `db` restart policy `unless-stopped`; row counts unchanged (seed not duplicated); `/api/docs` and `/api/openapi.json` 200 on `:8000` and through nginx on `:8080`; unknown path through nginx returns `{"code":"NOT_FOUND",...}`; old `/docs` 404 |

| T-015 | Rehearsal of `0002` on restored `edu_crm-20260915T154157Z-before-t014-workers.dump` | Upgrade `0001 → 0002`; `alembic check` clean; 8 of 8 columns `ru-RU-x-icu`; row counts unchanged |
| T-014, T-015, T-016 | Backup `edu_crm-20260915T155449Z-before-0002-and-web.dump`; `docker compose up -d --build api web` | `api` and `web` healthy; live `alembic_version` `0002`; 8 of 8 columns `ru-RU-x-icu`; row counts unchanged; `/`, `/interactions`, `/tasks`, `/analytics` return 200 (SPA fallback); request with `X-Forwarded-For: 203.0.113.77` logged as `172.18.0.1` (0 occurrences of the spoofed address) |
| T-016 | Lead re-run after review fixes | `npm run lint` clean; `npm test` 28 passed; `npm run build` success |
| T-016 | Browser (Claude Browser pane) on `http://localhost:8080/tasks` | Page renders with data; ticking a task updates the checkbox and sidebar counter (8 → 7) without reload; requests: `PATCH /tasks/1`, `GET /tasks`, and `GET /launches` (likely a window-focus refetch, see I-008); task unticked afterwards |
| T-021 (partial) | `pytest tests/test_security.py tests/test_oidc.py` | 31 passed |
| T-021, T-022 | Full backend suite with Keycloak sessions, CSRF, role policies (fake identity provider) | 114 passed; CI run 34935661251 success |
| T-023 | Suite with audit trail; backup `edu_crm-20260915T161918Z-before-0004-audit.dump`; API rebuilt | 130 passed; live `alembic_version` `0004`; existing row counts unchanged; `/api/v1/audit/recent` → 401 without session |
| Security fixes | Full suite; backup `edu_crm-20260915T162638Z-before-0005-login-binding.dump`; API rebuilt | 140 passed; live `alembic_version` `0005`; existing row counts unchanged; login start through nginx 302 and sets `edu_crm_login` scoped to `/api/v1/auth`; callback without that cookie → `/?auth_error=LOGIN_EXPIRED`; `/api/v1/launches` 401; `/api/docs/oauth2-redirect` 200 |
| Security finding 6 | Login rate limit in nginx (config copied into the running `web` container, `nginx -t` OK) | 30 rapid `GET /api/v1/auth/login`: 21 × 302, 9 × 429 with `{"code":"RATE_LIMITED",...}` (`application/json`); `/api/v1/launches` 401, `/tasks` 200, Keycloak discovery through `/auth/` 200 |
| T-020 | `scripts/generate-dev-secrets.sh`; backup `edu_crm-20260915T160853Z-before-0003-keycloak.dump`; `docker compose up -d --build keycloak-db-init keycloak api` | Init job exited 0 and created database `keycloak` owned by role `keycloak`; Keycloak 26.7.3 healthy (`/auth/health/ready` on port 9000); API healthy; live `alembic_version` `0003`; existing tables' row counts unchanged; `deploy/local/` gitignored (only variable names printed) |
| T-020 | HTTP checks through nginx (new `nginx.conf` copied into the running `web` container and reloaded) | `GET /api/v1/auth/login?next=/tasks` → 302 to `http://localhost:8080/auth/realms/edu-crm/protocol/openid-connect/auth` with `response_type, client_id, redirect_uri, scope, state, nonce, code_challenge, code_challenge_method`; Keycloak login page 200 with title «Вход Образование CRM» and login form; discovery from the API container: issuer `http://localhost:8080/auth/realms/edu-crm`, token and JWKS endpoints on `http://keycloak:8080`, one RS256 signing key; `GET /api/v1/launches` → 401 `UNAUTHENTICATED`; `/api/docs` 200 |

## Delegated work

| Agent task | Result | Evidence |
|---|---|---|
| Security review of Keycloak authentication (read-only subagent) | Verdict "acceptable after fixes": 1 HIGH, 3 MEDIUM, 5 LOW (see table below) | Reviewer reproduced the HIGH finding on a throwaway database; 114 tests passed during review |
| Frontend login integration T-024 (subagent, `frontend/src`) | Auth gate, login redirect, CSRF header, real profile, logout, role-aware UI; 48 tests | Lead re-ran lint (clean), `npm test` (48 passed), build (success); independent review in progress; no browser sign-in (D-130) |
| Frontend restructure (subagent, files limited to `frontend/`) | Routed pages, TanStack Query, error codes, 23 then 28 tests, ESLint | Lead re-ran lint/test/build; independent reviewer (read-only subagent) verdict "accept after fixes" with 4 medium and 6 low findings; the same subagent fixed all except the accepted brief `overdue` flicker; fixes re-verified by the lead |
| Keycloak realm spike (subagent, files limited to `deploy/keycloak/`) | `deploy/keycloak/realm-edu-crm.json` created; image `26.7.3` | In a throwaway container: realm `edu-crm` (ru default), roles `crm-user`/`crm-supervisor`/`crm-admin`, client `edu-crm-api` confidential with standard flow only and PKCE S256, direct password grant refused (`unauthorized_client`), client secret equals the environment value, three synthetic users each with one role, passwords from environment accepted and the literal placeholder rejected, `roles` claim present in ID token/userinfo/access token; health on port 9000 needs `KC_HEALTH_ENABLED=true`; image has bash but no curl/wget; about 629 MiB idle in dev mode. Containers removed. Lead review of the file pending at T-020 |

## Security review findings (authentication, commit `4f0cb41`)

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | HIGH | Row lock during revalidation returns the stale in-memory session, so concurrent requests reuse a rotated refresh token and revoke a legitimate session | Fixed: locked select with `populate_existing`; test reproduces the stale identity-map case |
| 2 | MEDIUM | A Keycloak outage (network error, 5xx, signing keys unavailable) revokes sessions instead of returning 503 | Fixed: `OIDCUnavailable` → 503 without revocation; test |
| 3 | MEDIUM | Login CSRF: the callback is not bound to the browser that started the login | Fixed: `edu_crm_login` cookie hash in `login_states` (migration `0005`); test with a planted callback in a second browser |
| 4 | MEDIUM | Logout does not end the Keycloak SSO session server-side | Fixed: back-channel logout by refresh token; logout skips revalidation and works while Keycloak is down; tests |
| 5 | LOW | A refresh response without `id_token` keeps old roles | Fixed: treated as rejection; test |
| 6 | LOW | `GET /auth/login` writes a row per request without rate limiting | Fixed: nginx `limit_req` (verified) and cap of pending logins (429, test) |
| 7 | LOW | ID token `azp` and `iat` age not checked | Fixed in `oidc.py`; tests |
| 8 | LOW | Two simultaneous first logins for one account can hit the unique constraint (500) | Fixed: `INSERT … ON CONFLICT` upsert; repeat-login test |
| 9 | LOW | Route-policy test matches path only, not method + path | Fixed: method + path, plus a consistency check that exposed a larger gap — FastAPI 0.141 keeps included routers as wrappers, so auth and audit routes had been skipped; the test now descends into them and asserts they are found |

## Checkpoints and versions

| Commit | Task | Verification |
|---|---|---|
| `7381a60` | T-001 specification and tracking documents | Documentation only |
| `a111283` | T-002 backup and restore scripts | Restore round trip with identical row counts |
| `443b8d8` | T-010, T-011 PostgreSQL only, tests on PostgreSQL | 9 tests; CI run 34902955520 success |
| `b90d7ff` | T-012 Alembic baseline, entrypoint migrations, stamping of existing databases | 13 tests; rehearsal on restored copy; live dev database stamped without data loss |
| `b8611f6` | T-013 error-code catalogue and handlers | 43 tests; CI run 34933768428 success |
| `c2c1366` | T-014 seeding in entrypoint, Swagger under `/api` | 45 tests; API rebuilt and checked |
| `6ed8c10` | T-015 per-column Russian collation (migration `0002`) | 47 tests; rehearsal on restored backup; live dev database migrated with row counts unchanged |
| `9806c8a` | Keycloak login design and decisions D-122–D-127 | Documentation only |
| `c598b7f` | T-016 frontend restructure (routing, TanStack Query, tests, lint) | 28 frontend tests, lint, build; independent review fixed; browser check |
| `a5ba27d` | T-014 web healthcheck, restart policies, forwarded-header trust | `web` healthy; spoofed `X-Forwarded-For` not logged |
| `5ff2050` | Frontend lint and tests in CI | CI configuration |
| `4f0cb41` | T-021/T-022 Keycloak sessions, CSRF, role policies | 114 tests; CI run 34935661251 success |
| `4d8a9dc` | T-020 Keycloak in Compose behind nginx, generated local secrets | Compose checks over HTTP (see evidence) |
| `52bc6d2` | Migrations and seeding need only `DATABASE_URL` | CLI regression test |
| `ddabb53` | T-023 audit trail and recent actions (backend) | 130 tests; live migration `0004` |
| `15c6caf` | Security review fixes (9 findings), login rate limit, route discovery fix | 140 tests; live migration `0005`; nginx rate limit verified |

## Versions

| Tag | Commit | Contents | Verification | Limitations | Preview |
|---|---|---|---|---|---|
| `ai-m1-foundation-20260915` | `5ff2050` | M1: PostgreSQL only, Alembic, Russian collation, error codes, container entrypoint, Swagger under `/api`, healthchecks, routed frontend with tests | Backend 47 tests, frontend 28 tests, CI green; migrations rehearsed on restored backups | No authentication | Stop the current stack first (`docker compose stop`, volumes kept). Then `git worktree add ../edu-crm-m1 ai-m1-foundation-20260915 && cd ../edu-crm-m1 && cp .env.example .env && COMPOSE_PROJECT_NAME=edu-crm-m1 docker compose up --build -d` — the separate project name gives it its own volumes; open http://localhost:8080 |

## Blockers and owner checks

| Item | Why | What the owner can do |
|---|---|---|
| Browser sign-in with a demo account through Keycloak | Agents must not type passwords into login forms (D-130) | After `docker compose up --build -d`, open http://localhost:8080 and sign in as `anna.demo`, `pavel.demo` or `irina.demo` with the passwords in `deploy/local/keycloak.env` |
