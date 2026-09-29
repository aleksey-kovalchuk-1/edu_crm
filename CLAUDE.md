# UniCRM — notes for AI assistants and new developers

**The laptop stack is production.** `docker compose -f compose.yaml -f compose.public.yaml` on the owner's Mac
serves https://unicrm.tech through a Cloudflare tunnel. Never restart, migrate or edit it to "try something":
use an isolated stack or the test database. Merges, deploys and pushes need the owner's explicit approval.

## Stack

- Backend: FastAPI (Python 3.12), SQLAlchemy 2, Alembic (`backend/migrations/versions/`), PostgreSQL only.
- Frontend: React 19 + TypeScript + TanStack Query + Vite, tests with Vitest (`frontend/src/**/*.test.tsx`).
- Auth: Keycloak 26 (realm `edu-crm`). Roles: `crm-user` (КАМ), `crm-supervisor` (Руководитель), `crm-admin`
  (Администратор); `crm-superadmin` is a composite of admin + supervisor.
- Services in `compose.yaml`: db, keycloak, api, web (nginx), notifier (same image as api).

## Commands

```bash
cp .env.example .env && scripts/generate-dev-secrets.sh && docker compose up --build -d   # local stack
cd backend && ../.venv/bin/python -m pytest -q          # needs PostgreSQL; TEST_DATABASE_URL picks another server
cd frontend && npx vitest run && npx tsc -b && npx eslint . && npx vite build
python3 scripts/generate-review-samples.py              # synthetic samples in docs/samples
```

Deploy (owner-approved only): merge the PR → `git merge --ff-only origin/main` in the main checkout → tag
rollback images (`docker image tag "edu-crm-${i}" "edu-crm-${i}:rollback-<sha>"`, braces required in zsh) →
`bash scripts/deploy-public.sh` (encrypted backups first, then releases; migrations run when the API starts).

## Rules

- The repository is **public**. Never commit production data, backups, secrets (`deploy/local/` is ignored),
  tunnel credentials or the customer's real files — they contain personal data. Use `docs/samples/` instead.
- Tests use isolated databases; never point tests or scripts at the production database. Don't copy production
  env files into worktrees — generate throwaway secrets.
- Errors: `AppError(ErrorCode.X, 'Russian message')` → `{code, message, details}`. User-facing text is Russian.
- Every behaviour change: failing test first, then code; run the full backend and frontend suites before a PR.
- Decisions go into `docs/decisions.md` (D-numbers) with the owner's words as the source.
- LMS and the website stay stubs until the customer's contracts arrive (D-233, D-246); no invented contracts.
- Learner questionnaires and applicants' personal data are not imported (D-235, D-247).

## Where to look

`docs/REVIEW.md` (start here) · `docs/decisions.md` · `docs/todo.md` · `docs/delivery/` (architecture) ·
`docs/api/` · `docs/operations/` (backups, hosting reliability).
