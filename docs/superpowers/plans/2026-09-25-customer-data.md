# Customer Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add supplier companies and contacts, protected learner profiles, and non-payment course applications with preview/apply imports.

**Architecture:** Add additive PostgreSQL tables and nullable links, keeping existing product text and IDs. Put each API domain in a focused router; parse imports in memory and revalidate at apply. Fetch sensitive learner details through a separately protected endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React, TypeScript, TanStack Query, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-customer-data-design.md`

## Global Constraints

- No real personal data in the working database, repository, audit or errors.
- Preserve `ITProduct.vendor`, contract and interaction product references, and reports.
- Apply no paid status from the JSON filename; initial status is `unconfirmed_by_data`.
- Validate access on the server; full learner details are supervisor/admin only.
- Use synthetic rows in tests until the two original spreadsheets are provided.

## Review Focus

- Multiple contacts at one company must attach to their own products; model/API tests exercise cross-company rejection.
- A repeat import with empty cells must retain populated learner fields; import tests exercise this.
- Conflicting email and phone matches must require manual resolution; matching tests exercise this.
- A direct request to a learner ID by a regular user must fail; route tests exercise this.
- A database dump or audit must not reveal document values; encryption and audit tests exercise this.

---

### Task 1: Supplier catalog and compatibility

**Files:** `backend/app/models.py`, `backend/migrations/versions/0018_vendor_companies.py`, `backend/app/vendor_routes.py`, `backend/app/main.py`, `backend/app/catalog_routes.py`, `backend/tests/test_vendor_catalog.py`.

**Interfaces:** `VendorCompany`, `VendorContact`, `ITProduct.company_id`, `GET/POST/PATCH /api/v1/vendor-companies`, `GET/POST/PATCH /api/v1/vendor-contacts`; product response adds `company_id` and `vendor_contacts` without removing fields.

- [ ] Write model tests for one company with two products and one shared contact, and a migration test that retains an existing product and contract.
- [ ] Run focused tests and confirm missing schema/model failure.
- [ ] Add tables, association table, nullable FK, exact-vendor backfill, relationships and compatibility output.
- [ ] Run focused tests and migration check until green.
- [ ] Write API tests for role rules, search, deactivate and cross-company product rejection; confirm red.
- [ ] Implement vendor routes and register router; run tests to green.
- [ ] Commit `feat: add supplier companies and product contacts`.

### Task 2: Protected learner profiles

**Files:** `backend/app/models.py`, `backend/migrations/versions/0019_learners.py`, `backend/app/learner_routes.py`, `backend/app/learner_crypto.py`, `backend/app/settings.py`, `backend/app/main.py`, `backend/tests/test_learners.py`.

**Interfaces:** `Learner`, `GET/POST/PATCH /api/v1/learners`, `GET /api/v1/learners/{id}`; `LEARNER_DATA_ENCRYPTION_KEY` is separate from the session key.

- [ ] Write tests for incomplete profile, string identifiers, encrypt/decrypt, forbidden direct detail, safe list/audit; confirm red.
- [ ] Add migration and model with optional fields, encrypted sensitive columns, safe list schema and full detail schema.
- [ ] Implement separate key validation and server role dependencies; never include document values in logs/errors.
- [ ] Run focused tests and migration check; commit `feat: add protected learner profiles`.

### Task 3: Applications and import pipeline

**Files:** `backend/app/models.py`, `backend/migrations/versions/0020_course_applications.py`, `backend/app/customer_imports.py`, `backend/app/customer_import_routes.py`, `backend/app/main.py`, `backend/tests/test_customer_imports.py`.

**Interfaces:** `CourseApplication`, `POST /api/v1/customer-imports/{kind}/preview`, `POST /api/v1/customer-imports/{kind}/apply`; `kind` is `vendors`, `learners`, or `applications`.

- [ ] Write tests for five applications plus `null`, repeat import, duplicate external number, ambiguous learner match, product splitting and row reports; confirm red.
- [ ] Add application table with unique external number and unconfirmed status.
- [ ] Implement bounded in-memory XLS/XLSX/JSON parsing, column mapping, preview and transactional apply; protect sensitive diagnostics.
- [ ] Run focused tests and full backend suite; commit `feat: import supplier learner and course application data`.

### Task 4: Interface and documentation

**Files:** `frontend/src/api/customerData.ts`, `frontend/src/pages/VendorsPage.tsx`, `frontend/src/pages/LearnersPage.tsx`, `frontend/src/pages/ApplicationsPage.tsx`, `frontend/src/pages/CustomerImportsPage.tsx`, navigation/routes, focused frontend tests, `docs/api/customer-data.md`, `docs/operations/backup.md`.

**Interfaces:** Typed calls for the Task 1–3 endpoints, role-gated detail view and preview/apply workflow.

- [ ] Write page tests for list/card, filters, full profile role gate, safe errors and import preview/apply; confirm red.
- [ ] Build pages using existing layout, form and query patterns; show supplier contacts in product catalog.
- [ ] Document fields, access, import columns and backup prerequisite.
- [ ] Run frontend tests, lint, type/build, backend suite, Alembic check and diff check.
- [ ] Commit `feat: show customer data and document import contracts`.
