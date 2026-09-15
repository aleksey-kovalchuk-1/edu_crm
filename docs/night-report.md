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

## Checkpoints and versions

No commits or tags on the working branch yet.

## Blockers

None.
