# Protected Customer Data Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create and verify encrypted database and attachment backups before real learner data is allowed in a working CRM environment.

**Architecture:** Stream `pg_dump` and the attachment archive directly into `age` encryption, never into a plaintext disk file. Restore by decrypting through a pipe into a newly named database or test location. Keep the public recipient on the backup host and the private identity separately.

**Tech Stack:** Bash, Docker Compose, PostgreSQL `pg_dump`/`pg_restore`, `age` CLI, shell integration tests.

**Spec:** `docs/superpowers/specs/2026-09-26-template-import-antifraud-design.md`; independent of the importer and alert tables, but required before real personal data is loaded.

## Global Constraints

- Do not use or overwrite any existing production backup, database, volume or private key. All validation uses a synthetic test database and temporary directory.
- Never write a plaintext dump/archive to disk, terminal output, repository or audit. Disable shell tracing around key material.
- Backup generation fails closed when `age` or a configured age recipient is absent; restore fails closed when `BACKUP_AGE_IDENTITY_FILE` is absent.
- Restore only to a new database name, retaining the current `db-restore.sh` non-overwrite guarantee.
- `LEARNER_DATA_ENCRYPTION_KEY`, `FRAUD_MATCH_KEY` and age identities are managed separately from encrypted backup files; none is committed to Git.

## Review Focus

- A failed `pg_dump`, `age` process or interrupted run must never leave a final-looking backup; Task 1 tests pipeline errors and `.partial` cleanup.
- An encrypted but corrupted file must be rejected before a restore database is created; Task 2 tests this.
- A missing recipient/key must stop the script before any plaintext dump starts; Task 1 tests this.
- Attachment bytes must receive the same protection as database rows; Task 2 tests both archive types.
- Rotation must preserve the ability to decrypt old backups until retention expires; Task 3 documents and tests an old/new recipient restore.

---

### Task 1: Encrypt database backups at creation

**Files:** Modify `scripts/db-backup.sh`; create `scripts/tests/test-encrypted-backup.sh`; update `docs/operations/backup.md`.

**Interfaces:** `BACKUP_AGE_RECIPIENT` is an `age1...` public recipient. Final artifact has suffix `.dump.age` and is printed only after the full pipeline succeeds. `age` is a required host dependency, not silently downloaded by the script.

- [ ] Write a shell integration test with synthetic `docker compose exec` output and a temporary backup directory: no recipient or no `age` must exit before `pg_dump`; a failed producer or encryptor must leave no final `.dump.age` file. Confirm these tests fail against the current plaintext script.

  ```bash
  if BACKUP_DIR="$test_dir" BACKUP_AGE_RECIPIENT='' scripts/db-backup.sh synthetic; then exit 1; fi
  test "$(find "$test_dir" -name '*.dump.age' | wc -l)" -eq 0
  ```
- [ ] Implement `umask 077`, `set -o pipefail`, executable/key checks and a temporary encrypted output:

  ```bash
  command -v age >/dev/null || { echo 'age is required' >&2; exit 2; }
  : "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT is required}"
  age -r "$BACKUP_AGE_RECIPIENT" -o /dev/null </dev/null
  docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc |
    age -r "$BACKUP_AGE_RECIPIENT" -o "$partial"
  mv "$partial" "$file"
  ```

  Use a trap to remove only the current `.partial` file on failure. Require a private backup directory and fail if the final path already exists. Never create a plaintext `.dump` or echo the recipient/private key. Keep the label validation and existing `BACKUP_DIR` behavior.
- [ ] Run `bash -n`, the shell test, and a real `age` round-trip on a synthetic dump in a temporary directory. Confirm output permissions are 0600 or stricter. Commit.

### Task 2: Safe verification, restore and attachment archives

**Files:** Modify `scripts/db-restore.sh`, `scripts/attachments-backup.sh`; create `scripts/attachments-verify.sh`; extend `scripts/tests/test-encrypted-backup.sh` and `docs/operations/backup.md`.

**Interfaces:** `BACKUP_AGE_IDENTITY_FILE` points to an age identity file outside the repo. `db-restore.sh <file.dump.age> <new-db>` decrypts twice: first to `pg_restore --list`, then to `pg_restore` into the new database. `attachments-verify.sh <file.tar.gz.age>` lists an archive after streaming decryption without extracting it.

- [ ] Write tests for missing/wrong identity, truncated ciphertext, existing target DB, successful synthetic restore to a new DB, and attachment archive verification. Assert the restore target is not created when preflight decryption fails.

  ```bash
  if BACKUP_AGE_IDENTITY_FILE="$wrong_key" scripts/db-restore.sh "$encrypted" crm_restore_test; then exit 1; fi
  test "$(fake_database_exists crm_restore_test)" = false
  ```
- [ ] Before `createdb`, run `age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$dump" | docker compose exec -T db pg_restore --list >/dev/null` with `pipefail`. Only after success create the new DB and stream the decrypt result to `pg_restore --exit-on-error`. Preserve target-name validation. Use the same streaming encryption pattern for `attachments-backup.sh`, with `.tar.gz.age` output and no plaintext tarball.
- [ ] Run shell tests and a temporary synthetic PostgreSQL/attachment round-trip. Inspect the temporary backup directory for only encrypted artifacts; compare restored row counts and attachment member names. Commit.

### Task 3: Key custody, rotation and readiness gate

**Files:** Modify `scripts/db-backup.sh`, `scripts/attachments-backup.sh`; update `docs/operations/backup.md`, `README.md`; extend `scripts/tests/test-encrypted-backup.sh`.

**Interfaces:** Public recipients may be listed in `BACKUP_AGE_RECIPIENTS_FILE` for rotation; private identities remain outside the repository and are passed only to restore. The documented readiness checklist is the operational gate for real customer data.

- [ ] Document how an operator generates an age identity, stores its private part separately, configures recipient(s), retains old identities through the backup retention window, and tests restoration. Include explicit handling for `LEARNER_DATA_ENCRYPTION_KEY` and `FRAUD_MATCH_KEY` recovery without placing those secrets in the same backup directory.
- [ ] Add a real round-trip check that a backup encrypted to old and new recipients can be read using either identity; document a tested procedure to retire an old identity only after old encrypted copies expire. Keep tests on synthetic content.

  ```bash
  printf 'synthetic only' | age -R "$recipients_file" -o "$encrypted"
  test "$(age -d -i "$old_identity" "$encrypted")" = 'synthetic only'
  test "$(age -d -i "$new_identity" "$encrypted")" = 'synthetic only'
  ```
- [ ] Update the README to state that real learner imports remain disabled operationally until encrypted DB and attachment backups, access restrictions, retention and a restore rehearsal are verified. Run `bash -n`, shell tests, repository checks and the relevant backend migration tests; commit.

## Completion gate

The readiness claim requires fresh evidence from a synthetic encrypted backup and restore, including attachments and key recovery. No real learner workbook is applied to the working database during this plan.
