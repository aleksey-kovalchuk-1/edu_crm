# Customer Data Antifraud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flag contradictory imports and suspicious identity reuse for human review without external APIs or automatic fraud judgments.

**Architecture:** Run versioned, deterministic rules on normalized input and existing CRM records. Persist only safe alert metadata and manual decisions. Use a separate keyed HMAC fingerprint for document equality, while existing document ciphertext remains protected by `LEARNER_DATA_ENCRYPTION_KEY`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, cryptography/Python HMAC, React, TypeScript, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-26-template-import-antifraud-design.md`; execute after `2026-09-26-template-import-implementation.md` so batch IDs are available.

## Global Constraints

- No external payment, identity or Yandex Disk API, and no fabricated payment evidence. Existing applications remain `unconfirmed_by_data`.
- A signal is a review priority, not a fraud verdict. No rule automatically blocks a person or modifies a payment state.
- Never put SNILS, passport values, phone/email values, source rows or filenames in alerts, audit payloads or diagnostic strings.
- Supervisor/admin are the only roles allowed to list, inspect or decide alerts. Full learner cards keep their existing server-side role gate.
- Only synthetic values enter tests or the development database; actual supplied files are read-only structural inputs.

## Review Focus

- Re-importing an application number with another learner or course must not silently overwrite stored fields; Task 1 tests both changes.
- Two different learners legitimately sharing a family phone must create a reviewable warning without automatic merge or rejection; Task 3 tests it.
- Equal SNILS/passport pairs must match despite random Fernet ciphertext, but ciphertext and alert JSON must not reveal the identifier; Task 4 tests this.
- A repeat batch must not create duplicate open alerts, and an old reviewer decision must remain auditable; Tasks 2 and 5 test deduplication/history.
- An authorized-but-stale reviewer must not overwrite a later decision; Task 5 tests conditional updates.

---

### Task 1: Pure conflict rules and safe import behavior

**Files:** Create `backend/app/fraud_rules.py`; modify `backend/app/customer_imports.py`; test `backend/tests/test_fraud_rules.py` and `backend/tests/test_customer_imports.py`.

**Interfaces:** `FraudSignal(rule_code, rule_version, priority, entity_type, entity_id, related_entity_id, row_number)` with no source values; `evaluate_application(existing, proposed_learner_id, course, stream_number, row_number) -> list[FraudSignal]`.

- [ ] Write a failing unit test where a repeated external number has a changed course or a different learner. Assert a high-priority `application_number_conflict`, while unchanged input emits none. Write a route test proving the conflicting row leaves stored course, stream and learner unchanged.

  ```python
  signals = evaluate_application(existing, existing.learner_id, 'Другой курс', existing.stream_number, 2)
  assert [signal.rule_code for signal in signals] == ['application_number_conflict']
  assert evaluate_application(existing, existing.learner_id, existing.course, existing.stream_number, 2) == []
  ```
- [ ] Run the focused tests and confirm current importer overwrites the changed course.
- [ ] Implement the pure comparison and call it before the existing application's update path:

  ```python
  changed = (existing.learner_id != proposed_learner_id or
             existing.course != course or existing.stream_number != stream_number)
  if changed:
      return [FraudSignal('application_number_conflict', 1, 'high',
                          'course_application', existing.id, None, row_number)]
  ```

  Re-run learner matching for incoming contact data before deciding whether the learner changed. A conflict produces a blocked row and safe rule code, not an update; a byte-for-byte semantic repeat remains `updated`/no-op for compatibility.
- [ ] Run focused tests, including five synthetic JSON applications plus `null`; commit the rule and importer guard.

### Task 2: Alert persistence and deduplication

**Files:** Create `backend/migrations/versions/0022_fraud_alerts.py`, `backend/app/fraud_alerts.py`; modify `backend/app/models.py`, `backend/app/customer_import_routes.py`; test `backend/tests/test_fraud_alerts.py`, `backend/tests/test_migrations.py`.

**Interfaces:** `FraudAlert(id, dedupe_key, rule_code, rule_version, priority, status, entity_type, entity_id, related_entity_id, batch_id, row_number, created_at, updated_at, reviewed_by_user_id, reviewed_at, resolution_code)`; `upsert_alert(db, signal, batch_id) -> FraudAlert`.

- [ ] Write a failing DB test that applies the same conflict twice and expects one open alert. Assert only IDs, rule metadata and safe codes appear in the stored row and audit. Add a migration test for an existing application surviving the new table.

  ```python
  upsert_alert(db, signal, batch_id=1)
  upsert_alert(db, signal, batch_id=2)
  assert db.scalar(select(func.count()).select_from(FraudAlert)) == 1
  ```
- [ ] Add migration `0022` after `0021`, with FKs to `customer_import_batches`/`users`, status and priority checks, an index for queue sorting and unique `dedupe_key`. Build the dedupe key from the rule/version plus sorted stable entity IDs, or batch ID and row number if no entity exists; never use raw values.
- [ ] Implement `upsert_alert` in the same transaction as import application. Repeated detection reuses the existing alert; it does not silently reopen a reviewed decision. Store `rule_code`, `row_number` and safe entity IDs in `record_event`, never a proposed value. Run migration and focused tests; commit.

### Task 3: Shared contacts, ambiguous matches and velocity

**Files:** Modify `backend/app/fraud_rules.py`, `backend/app/customer_imports.py`, `backend/app/settings.py`; test `backend/tests/test_fraud_rules.py`, `backend/tests/test_customer_imports.py`, `backend/tests/test_settings.py`.

**Interfaces:** `evaluate_shared_contact(existing_learner_ids, incoming_learner_id) -> list[FraudSignal]`; `evaluate_import_velocity(rows, recent_batch_count, row_limit=500, hourly_limit=10) -> list[FraudSignal]`.

- [ ] Write tests for a shared contact across distinct learners (warning), the same contact on one learner (no warning), conflicting phone/email candidates (manual choice plus signal), 501 rows in one batch (warning), and 11 applies by one actor in an hour (warning). Confirm each fails before implementation.

  ```python
  assert evaluate_shared_contact({1, 2}, incoming_learner_id=2)[0].rule_code == 'shared_contact'
  assert evaluate_shared_contact({2}, incoming_learner_id=2) == []
  assert evaluate_import_velocity(rows=501, recent_batch_count=0)[0].rule_code == 'import_velocity'
  ```
- [ ] Add pure rules. `shared_contact` never blocks a row by itself. `learner_match_conflict` blocks automatic merge until a supervisor chooses a candidate; the chosen ID must be among server-derived candidates and the decision must be audited. `import_velocity` warns at the documented defaults; configuration values are validated as positive integers.
- [ ] Wire rules into preview without any writes and into apply in the batch transaction. Add rule codes and priorities to the report without personal values. Run focused and full backend tests; commit.

### Task 4: Protected document equality

**Files:** Create `backend/app/fraud_fingerprint.py`, `backend/app/backfill_fraud_fingerprints.py`, `backend/migrations/versions/0023_learner_fingerprints.py`; modify `backend/app/models.py`, `backend/app/settings.py`, `backend/app/learner_routes.py`, `backend/app/customer_imports.py`, `backend/app/main.py`, `scripts/generate-dev-secrets.sh`; test `backend/tests/test_fraud_fingerprints.py`, `backend/tests/test_learners.py`, `backend/tests/test_settings.py`.

**Interfaces:** `fingerprint(kind, normalized_value, key_bytes) -> str`; `LearnerFingerprint(learner_id, kind, key_version, digest)` indexed by `(kind, key_version, digest)`. Optional `FRAUD_MATCH_KEY` and `FRAUD_MATCH_KEY_VERSION` settings are distinct from session and learner encryption keys.

- [ ] Write failing tests proving equal normalized SNILS and passport series+number yield equal keyed fingerprints for different learners, different values differ, and random Fernet ciphertext differs. Assert DB rows, route JSON and audit do not contain source values. Test absent key disables this rule explicitly without blocking unrelated CRM routes.

  ```python
  assert fingerprint('snils', '12345678901', key_bytes) == fingerprint('snils', '12345678901', key_bytes)
  assert fingerprint('snils', '12345678901', key_bytes) != fingerprint('snils', '12345678902', key_bytes)
  assert '12345678901' not in json.dumps(head.get('/api/v1/fraud-alerts').json())
  ```
- [ ] Add migration `0023` after `0022` for the fingerprint table. Implement normalization (`snils`: digits only; `passport_pair`: four series digits plus six number digits) and `hmac.new(key, f'{kind}:{value}'.encode(), hashlib.sha256).hexdigest()`. Parse a 32-byte base64 key, reject reuse of other application keys and store its version. Update fingerprints atomically on learner create/edit/import; remove an old fingerprint when the corresponding field is cleared.
- [ ] Add a resumable, admin-run backfill command that decrypts existing learner identifiers in batches only when both keys are present, stores fingerprints, and prints counts without values. Never perform this backfill automatically on application startup or migration.
- [ ] Test duplicate-document signal creation and key-version mismatch. Document a maintenance-window rotation: pause document-equality alerts, switch to a new key/version, rebuild fingerprints by decrypting existing records with the learner key, verify coverage, then retire the old fingerprints/key. Do not claim the rule is active while coverage is incomplete. Run focused tests and commit.

### Task 5: Human review API and UI

**Files:** Create `backend/app/fraud_routes.py`, `frontend/src/api/fraudAlerts.ts`, `frontend/src/pages/FraudAlertsPage.tsx`, `frontend/src/pages/fraudAlerts.test.tsx`; modify `backend/app/main.py`, `frontend/src/app/App.tsx`, `frontend/src/app/navigation.ts`, `frontend/src/styles.css`, `docs/api/customer-data.md`; test `backend/tests/test_fraud_alerts.py`.

**Interfaces:** `GET /api/v1/fraud-alerts?status=&priority=` and `GET /api/v1/fraud-alerts/{id}` return safe metadata; `PATCH /api/v1/fraud-alerts/{id}` takes `{status, resolution_code, expected_updated_at}`. Allowed statuses: `open`, `in_review`, `cleared`, `confirmed`.

- [ ] Write backend role tests: `crm-user` gets 403 on list/detail/review; supervisor/admin can review; a stale `expected_updated_at` gets 409 and leaves the newer decision. Verify every decision creates an append-only audit event with actor/time/safe code.

  ```python
  assert manager.get('/api/v1/fraud-alerts').status_code == 403
  assert head.patch(f'/api/v1/fraud-alerts/{alert_id}', json={
      'status': 'cleared', 'resolution_code': 'legitimate_shared_contact',
      'expected_updated_at': prior_timestamp,
  }).status_code == 200
  ```
- [ ] Add the routes with bounded pagination, status/priority filters, state-transition validation and optimistic concurrency. Detail responses show rule labels, entity IDs and links; full learner values are fetched only through existing protected routes. A cleared alert remains in history, and repeat detection never overwrites its reviewer decision.
- [ ] Write failing frontend tests for queue filters, priority, safe links to records, review action and regular-user invisibility. Build the page using existing layout and query conventions, invalidate alert/audit queries after review, and use no document values in client cache.
- [ ] Document each rule, limits and manual procedure. Run full backend tests including migrations, all frontend tests, TypeScript, lint and production build. Commit.

## Completion gate

With synthetic data, prove alert deduplication, human decision history, privacy of responses/audit and unchanged payment status. Inspect `git diff --check` and the clean working tree. Do not use real workbook rows for anti-fraud calibration.
