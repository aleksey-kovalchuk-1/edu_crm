# Account roster and university access implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Each task uses a failing test before code.

**Goal:** Give all managers access to the ten supplied universities, make Irina the only head, and let her create administrator and manager accounts.

**Architecture:** A per-university team-visibility flag broadens the university data scope without granting global task permissions. Keycloak remains the identity source; a superadmin-only creation endpoint uses a temporary credential and the existing service account. An operator step reconciles the current demo accounts after encrypted backup.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Keycloak Admin API, React/Vite, PostgreSQL, Docker Compose.

**Spec:** `docs/design/account-roster-and-manager-access-2026-09-27.md`.

## Global constraints

- Keep customer files and `sources/` read-only; never commit passwords or Keycloak tokens.
- Preserve Keycloak subject IDs and CRM task/history foreign keys when renaming.
- Create no second `crm-superadmin` or `crm-supervisor`.
- Production changes follow an encrypted database and attachment backup, test run, and readback.

## Tasks

### 1. Share the ten university records

- [ ] Add failing tests for manager visibility of the ten partner universities and isolation of an unshared new university.
- [ ] Add migration and model field, scope logic, and idempotent partner-roster update.
- [ ] Run targeted and full backend tests; update access documentation.

### 2. Create accounts from the superadmin screen

- [ ] Add failing tests for Keycloak create/role/enable/failure rollback and server role/CSRF validation.
- [ ] Implement Keycloak client and a superadmin-only API; return a temporary password only in the creation response.
- [ ] Make the account directory show actual Keycloak accounts before first login.
- [ ] Add failing UI tests, then the create-account form and one-time credential display.
- [ ] Run backend and frontend suites, lint and build; update API and role documentation.

### 3. Reconcile and release working accounts

- [ ] Preview existing identities and user-provided naming/count preferences without disclosing secrets.
- [ ] Back up the running database and attachments; reconcile Irina and demo accounts without deleting history.
- [ ] Verify exactly one head/superadmin, the requested administrator/manager accounts and all ten shared universities.
- [ ] Deploy checked code, test login and API health, and provide a role-by-role access summary.
