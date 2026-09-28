# Archived: customer data (learners, supplier companies, course applications, customer imports)

Taken out of UniCRM on 28 Sep 2026 at the owner's request: these sections are no longer relevant and must
not be available in production. The code is kept here so it can be restored. See decision D-235 in
`docs/decisions.md`.

## What is here

- `frontend/pages/` — the former «Слушатели» (`LearnersPage`), «Компании» (`VendorsPage`),
  «Заявки на курсы» (`ApplicationsPage`) and «Загрузка данных» (`CustomerImportsPage`) screens and their test.
- `frontend/api/customerData.ts` — their API client.

These files are outside `frontend/`, so they are neither built, type-checked nor tested.

## What stays in the application

- Backend modules `vendor_routes.py`, `learner_routes.py`, `customer_import_routes.py` and
  `customer_imports.py`, the database models, migrations and existing data are unchanged.
- Their API is **not served** unless `CUSTOMER_DATA_ENABLED=true` is set for the API (default: off).
  The backend test suite switches it on, so the code stays tested while it is kept.
- «Проверка сигналов» (fraud alerts) is still available. Without imports it receives no new signals from
  customer data; alerts about archived records show the record number instead of a link.

## Restoring

1. Move the files back to `frontend/src/pages/` and `frontend/src/api/`.
2. Restore the four entries in `frontend/src/app/navigation.ts` and the routes in `frontend/src/app/App.tsx`.
3. Set `CUSTOMER_DATA_ENABLED=true` in `deploy/local/api.env` and redeploy.
