# Archived: customer data (learners, supplier companies, course applications, customer imports, fraud alerts)

Taken out of UniCRM on 28 Sep 2026 at the owner's request: these sections are no longer relevant and must
not be available in production. The code is kept here so it can be restored. See decisions D-235 and D-236
in `docs/decisions.md`.

## What is here

- `frontend/pages/` — the former «Слушатели» (`LearnersPage`), «Компании» (`VendorsPage`),
  «Заявки на курсы» (`ApplicationsPage`), «Загрузка данных» (`CustomerImportsPage`) and
  «Проверка сигналов» (`FraudAlertsPage`) screens and their tests.
- `frontend/api/customerData.ts` and `frontend/api/fraudAlerts.ts` — their API clients.

These files are outside `frontend/`, so they are neither built, type-checked nor tested.

## What stays in the application

- Backend modules `vendor_routes.py`, `learner_routes.py`, `customer_import_routes.py`,
  `customer_imports.py`, `fraud_routes.py` and the fraud rules, the database models, migrations and
  existing data (including stored alerts) are unchanged.
- Their API is **not served** unless `CUSTOMER_DATA_ENABLED=true` is set for the API (default: off).
  The backend test suite switches it on, so the code stays tested while it is kept.

## Restoring

1. Move the files back to `frontend/src/pages/` and `frontend/src/api/`.
2. Restore the entries in `frontend/src/app/navigation.ts` (fraud alerts sat in a «Данные клиентов» group)
   and the routes in `frontend/src/app/App.tsx`.
3. Set `CUSTOMER_DATA_ENABLED=true` in `deploy/local/api.env` and redeploy.
