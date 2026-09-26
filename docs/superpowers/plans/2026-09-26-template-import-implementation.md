# Customer Template Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept the two supplied Excel layouts, preview their mapping and safely turn synthetic rows into editable CRM cards.

**Architecture:** Extend the existing in-memory customer importer with a typed parsed-file result, exact template aliases and row warnings. Record only batch metadata and entity links on apply; leave uploaded bytes and cell values transient.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, openpyxl/xlrd, React, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-template-import-antifraud-design.md`

## Global Constraints

- No Yandex Disk or other external API calls. Real local workbooks are read-only and never become repository fixtures.
- No real personal data in the working database, tests, history, audit or logs. Use only synthetic values in write tests.
- Keep existing `ITProduct.vendor`, IDs and downstream contracts intact; `payment_status` remains `unconfirmed_by_data`.
- Full learner details and import writes remain supervisor/admin only, enforced on the server.
- The parser still limits uploads to 10 MB, 5000 data rows, 50 columns and 100 MB uncompressed XLSX content.

## Review Focus

- Malformed combined headers in `Загрузка пользователей.xlsx` must map to the correct field, never to a neighboring field; Task 1 tests all 30 headers.
- A numeric phone with 10 digits, a leading zero that Excel discarded, or a fractional value must be rejected rather than guessed; Task 2 tests these cases.
- A header-only workbook must preview as zero rows while the older catalog importer still rejects it; Task 3 tests both contracts.
- A failure after partial row processing must roll back cards, batch and row links together; Task 4 tests rollback.
- A regular CRM user must not learn learner document data from preview/history or direct detail routes; Tasks 3 and 5 test role and payload safety.

---

### Task 1: Exact template recognition

**Files:** Modify `backend/app/customer_imports.py`, `backend/app/importer.py`; test `backend/tests/test_customer_imports.py`. `read_upload()` keeps its current default behavior for catalog imports.

**Interfaces:** Add `CustomerFile(kind, template_version, headers, mapping, unmapped_headers, rows)`, `LEARNER_TEMPLATE_HEADERS` (the exact 30 names from the supplied first sheet), and `read_customer_file(kind, filename, content) -> CustomerFile`. Keep `read_rows()` as a compatibility wrapper until routes switch.

- [ ] Add a synthetic workbook test with the complete 30-header learner row and an auxiliary second sheet. Assert `mapping` covers all 30 named columns, `unmapped_headers == []`, one row is returned and the second sheet contributes none. Add the six vendor headers as a second parameterized case. The test must fail on the current 11 missing aliases.

  ```python
  headers = list(LEARNER_TEMPLATE_HEADERS)
  cells = [''] * len(headers)
  cells[0], cells[1], cells[3] = 'Тестов', 'Иван', 79000000001
  parsed = read_customer_file('learners', 'synthetic.xlsx', workbook(headers, [cells]))
  assert len(parsed.mapping) == 30
  assert parsed.unmapped_headers == []
  assert len(parsed.rows) == 1
  ```
- [ ] Run `/Users/alex/dev/edu-crm/.venv/bin/python -m pytest tests/test_customer_imports.py -q` from `backend` with the configured test database; confirm the new case fails for missing fields.
- [ ] Add only the 11 exact aliases listed in the spec. For example:

  ```python
  LEARNER_COLUMNS.update({
      'отчествопри наличии': 'middle_name',
      'номер телефона': 'phone',
      'населенный пункт регистрации': 'registration_locality',
      'учебное заведение по диплому': 'diploma_institution',
      'фамилия указанная в дипломе': 'diploma_last_name',
  })
  ```

  Include the other six exact normalized aliases from the spec, including the three dative-case headings; reject duplicate mappings to one CRM field. Return `template_version='customer-learners-v1'` or `'customer-vendors-v1'` for the matching layout, and `unmapped_headers` for nonempty unknown columns.
- [ ] Run the focused tests, then perform a read-only structural smoke check of the two local workbooks: print only row counts, recognized field names and unknown header names. Never print data cells. Commit the parser change.

### Task 2: Numeric phone conversion with explicit warnings

**Files:** Modify `backend/app/customer_imports.py`; test `backend/tests/test_customer_imports.py`.

**Interfaces:** Add `normalize_import_phone(value) -> tuple[str, list[str]]`; row warnings are added to the existing report entry and do not become audit payload values.

- [ ] Write tests for the template's 11-digit integer starting with `7` (converted to a string and reported with a warning), an 11-digit integer starting with `8`, an integer with 10 digits, an integer starting with `0` after Excel conversion, and a non-integral float. Keep the existing text-phone test unchanged. Confirm the accepted case fails first.

  ```python
  phone, warnings = normalize_import_phone(79000000001)
  assert phone == '79000000001' and len(warnings) == 1
  with pytest.raises(ImportRowError):
      normalize_import_phone(9000000001)
  ```
- [ ] Implement conversion only when the source value is an integer of exactly 11 digits beginning with `7` or `8`:

  ```python
  if isinstance(value, int) and not isinstance(value, bool):
      digits = str(value)
      if len(digits) == 11 and digits[0] in '78':
          return digits, ['Телефон был числом Excel; проверьте исходную ячейку']
      raise ImportRowError('Числовой телефон нельзя восстановить без проверки')
  ```

  Apply this to learner and vendor rows before validation. Keep document identifiers and postal codes text-only. Attach the warning to the current row, not a global message.
- [ ] Run focused tests, verify no phone value appears in diagnostics, and commit.

### Task 3: Preview metadata, mapping and empty templates

**Files:** Modify `backend/app/importer.py`, `backend/app/customer_imports.py`, `backend/app/customer_import_routes.py`; test `backend/tests/test_customer_imports.py` and `backend/tests/test_import_api.py`.

**Interfaces:** `POST /api/v1/customer-imports/{kind}/preview` returns existing `summary`/`rows` plus `template_version`, `mapping`, `unmapped_headers`. Both preview and apply accept an optional JSON `mapping` form field of `{crm_field: source_header}`; the server verifies each source header exists, each target is valid and no header or target is used twice. `POST .../apply` rejects a zero-row file with a safe validation error.

- [ ] Write API tests for a header-only customer workbook (preview `rows == 0`, apply rejected), an unknown nonempty column (reported, not silently imported), and a supervisor/regular-user access split. Add a regression test proving `POST /api/v1/imports` retains its existing empty-file error.

  ```python
  preview = upload(head, 'learners', 'preview', workbook(['Фамилия', 'Имя'], []), 'blank.xlsx')
  assert preview.json()['summary']['rows'] == 0
  assert upload(head, 'learners', 'apply', workbook(['Фамилия', 'Имя'], []), 'blank.xlsx').status_code == 422
  ```
- [ ] Add `allow_empty_rows: bool = False` to the shared `_split_header`/`read_upload` path and opt in only from the customer parser. Build metadata from the original header cells while preserving existing row-number behavior. Ensure duplicate CRM targets require explicit mapping resolution rather than silently using the last header.
- [ ] In the customer routes, use `read_customer_file()` and pass `.rows` to `CustomerImportRunner`. Validate the optional `mapping` form field on both requests and construct row dictionaries from that approved mapping. Return metadata in preview; verify apply re-reads and revalidates the uploaded bytes. Run focused API tests and commit.

### Task 4: Safe batch provenance and card links

**Files:** Create `backend/migrations/versions/0021_customer_import_batches.py`; modify `backend/app/models.py`, `backend/app/customer_imports.py`, `backend/app/customer_import_routes.py`; test `backend/tests/test_customer_imports.py`, `backend/tests/test_migrations.py`.

**Interfaces:** Add `CustomerImportBatch(id, kind, template_version, created_by_user_id, created_at, rows, valid, invalid, skipped, created, updated)` and `CustomerImportRowLink(batch_id, row_number, entity_type, entity_id, action)`. `GET /api/v1/customer-imports/history` returns bounded batch summaries; `GET /api/v1/customer-imports/history/{id}` returns safe row links. Apply report adds `batch_id` and `record_links` by row.

- [ ] Write a test that applies one synthetic vendor/learner/application row and checks links point to actual cards while history and audit contain no source filename, phone, SNILS, passport, or cell arrays. Add a forced database failure test asserting the entire apply transaction rolls back, including batch and links. Confirm missing-table failure first.

  ```python
  content = workbook(['Фамилия', 'Имя', 'Телефон'], [['Тестов', 'Иван', '79000000001']])
  result = upload(head, 'learners', 'apply', content, 'private-name.xlsx').json()
  assert result['record_links'][0]['entity_type'] == 'learner'
  assert 'private-name.xlsx' not in json.dumps(head.get('/api/v1/customer-imports/history').json())
  ```
- [ ] Create migration `0021` after `0020` with indexed FKs and checks for `kind` and action. Keep all columns additive and do not modify `catalog_imports` (it serves a different existing flow).
- [ ] Have the runner return per-row entity references internally; create the batch and row links in the same SQLAlchemy session before the existing `db.commit()`. Never store invalid row values. Implement bounded history routes with supervisor/admin access and audit summary counts only. Run focused and migration tests; commit.

### Task 5: Usable upload flow and synthetic demo

**Files:** Modify `frontend/src/api/customerData.ts`, `frontend/src/pages/CustomerImportsPage.tsx`, `frontend/src/pages/customerData.test.tsx`, `docs/api/customer-data.md`; create `scripts/generate-customer-demo-files.py`, `backend/tests/test_customer_demo_files.py`.

**Interfaces:** Typed preview metadata, row links and batch history. No client-side access to full learner data for `crm-user`.

- [ ] Write frontend tests for all recognized columns, unknown-column notice, a zero-row preview with disabled apply, numeric-phone warning, a post-apply card link, and the history list. Confirm the tests fail against the current upload page.

  ```tsx
  expect(await screen.findByText(/30 столбцов распознано/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Применить' })).toHaveProperty('disabled', true);
  ```
- [ ] Show column mapping and omissions above the row report; show links only for rows the server says were applied. Offer safe manual mapping for unknown or duplicate headings and send its choices to both preview/apply, with server validation. Preserve candidate selection and payment warning.
- [ ] Add a script that generates three clearly synthetic, editable demo files (vendor XLSX, learner XLSX with the exact combined headers and numeric phone, application JSON with one `null`) into an operator-chosen output directory. Add a test that parses all three through `read_customer_file()` and verifies counts/header mapping; never commit the generated files or copy supplied rows.
- [ ] Update API docs with the exact aliases and warnings. Run the complete backend suite, migration tests, complete frontend suite, TypeScript check, lint and production build. Commit the interface and docs.

## Completion gate

Confirm both supplied workbooks are structurally recognized by a read-only check, synthetic end-to-end uploads create editable cards, and the working tree is clean. Do not apply either supplied workbook to the working database.
