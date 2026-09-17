# Migration renumbering during integration

`ai/integration-candidate` merges three branches that were developed in parallel from
`ai/crm-foundation` at `0008_workflows` and independently added their own next migration:

| Branch | Original file | Original revision | Parent |
|---|---|---|---|
| `ai/phone-verification` | `0009_phone_verification.py` | `0009` | `0008` |
| `ai/file-ingestion` | `0009_ingestion_foundation.py` | `0009` | `0008` |
| `ai/file-ingestion` | `0010_documents.py` | `0010` | `0009` |

Both branches claimed revision `0009` against the same parent — a genuine Alembic
multiple-heads collision, not a text merge conflict (the files even have different
names, so `git merge` did not flag it).

## Resolution

Phone verification (reviewed and merged in PR #2) keeps its original revision id
unchanged. The file-ingestion migrations were shifted by one and rewired into a single
linear chain:

| File (in this branch) | Revision | Parent |
|---|---|---|
| `0009_phone_verification.py` | `0009` | `0008` (unchanged) |
| `0010_ingestion_foundation.py` | `0010` | `0009` (renamed from `0009`, parent changed from `0008`) |
| `0011_documents.py` | `0011` | `0010` (renamed from `0010`) |

Only the integration branch's copies were renamed; `ai/phone-verification` and
`ai/file-ingestion` themselves are untouched. Decision IDs D-165–D-173 in
`docs/decisions.md` (originally `ai/file-ingestion`'s own D-155–D-163, which also
collided — first with `ai/auth-registration`'s D-155–D-160, then with
`ai/phone-verification`'s renumbered D-161–D-163) and every in-repo cross-reference to
them were updated accordingly; see D-164/D-174 for the renumbering record.

## Verification

- `alembic heads` reports exactly one head.
- An empty database reaches that head via `alembic upgrade head` (`test_empty_database_is_migrated_to_head`).
- `test_downgrade_to_base_and_upgrade_again` walks the full chain down to `base` and back.
- No `alembic stamp` was used anywhere in this process; no `alembic_version` row was
  edited by hand.
