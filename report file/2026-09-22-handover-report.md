# UniCRM — Handover Report, 2026-09-22

Branch: `ai/phone-verification`. Commit at time of writing: `894b2d212d760b6153095257166e4eb9a2c58be0`
(pushed to `origin/ai/phone-verification`, same commit — working tree clean; see "Working directory
status" below). This report covers the current stage of work and is written for whoever picks up
this branch next.

## 1. Working directory status

- Branch: `ai/phone-verification`.
- `HEAD` = `origin/ai/phone-verification` = `894b2d2` — nothing to commit from this session; no
  uncommitted work was pending.
- Untracked, deliberately **not** committed (tooling/scratch, not project deliverables, no
  secrets found in them): `.claude/` (local Claude Code settings — permission-rule audit trail
  only, no credentials), `docs/superpowers/plans/` (planning-skill scratch files for the slices
  built this session), `skills-lock.json` (Claude Code skill-lock metadata). None of these were
  created by "other" contributors — they're this session's own tooling state, consistent with how
  every earlier slice this session also left them untracked.
- No secrets were found in anything reviewed. No changes attributable to other people/sessions
  were present in the working tree to sort out.

## 2. What has been done this stage

In rough chronological order (all on `ai/phone-verification`, all pushed):

- **Настройки (Settings) shell**: sidebar entry with a hover/click/keyboard submenu, 7 pages in
  the order the owner specified (Личный профиль, Организация, Уведомления, Безопасность,
  Пользователи и роли, Персональные данные, Резервное копирование).
- **Keycloak Admin API integration**: `crm-superadmin` role, `KeycloakAdminClient`
  (least-privilege service account, fails closed when unconfigured), deterministic superadmin
  bootstrap on container start, simple RBAC (one superadmin; everyone else a plain `crm-user`
  unless promoted by hand) — per the owner's explicit architecture decision.
- **Email infrastructure**: injectable `send_email` (logging stub or generic HTTP provider),
  admin-managed sender-identity catalog, safe test-send-to-self with rate limiting — mirrors the
  existing SMS-verification pattern.
- **Настройки → Аккаунт** (new tab) and **Настройки → Пользователи и роли** (filled in): logout,
  a superadmin-only user directory (count + login), and a real "pending Keycloak registration"
  approval flow (grants the baseline `crm-user` role to an account that can sign in but has no CRM
  role yet).
- **Личный профиль**: now hosts the real phone-verification panel (moved from the old standalone
  `/profile` route, which now redirects here).
- **Header/Задачи page design pass**: removed the site-wide "ОБРАЗОВАТЕЛЬНЫЕ ПАРТНЁРСТВА" eyebrow
  and the Задачи page's subtitle line; enlarged and promoted the view/scope tabs on Задачи; moved
  "Шаблоны планов" and the task counters into one smaller, right-aligned row below the tabs.
- A live deployment fix: the `api` container had lost its public-origin environment overrides
  (`PUBLIC_BASE_URL`/`OIDC_ISSUER`/`COOKIE_SECURE`) after a plain restart dropped the
  `compose.public.yaml` overlay, causing login to redirect to `localhost` for the real user —
  fixed by rebuilding with both compose files.

Test/build state as of this report (re-run fresh, not from memory):
- Backend: `384 passed` (`../.venv/bin/python -m pytest -q` from `backend/`), including the real
  Postgres migration suite and the RBAC access-policy invariant test.
- Frontend: `270 passed` (`npx vitest run`), ESLint clean, `tsc --noEmit` clean,
  `npm run build` succeeds.
- Live site (`https://unicrm.tech`): `/api/v1/health` → 200, `/` → 200, all six Compose services
  healthy.

## 3. Rostelecom LMS / website (CMS) API integration — compliance check (task item 2)

**Requirement** (`docs/specification.md`, "Data sources" and "Functional requirements"): collect
information from two external systems — the RTK IT School's **LMS** and its **Laravel CMS
website** — via API, in JSON, feeding an existing or new workflow interaction. The specification
itself says *"the API contract will be provided during discussions with the teams"* — i.e. the
real contract was never available to build against. `docs/decisions.md` D-008 (an owner decision,
present on this branch) already authorizes building this as a **labelled mock** until the real
contract arrives.

**Finding — on this branch (`ai/phone-verification`): no implementation exists at all.**
Verified by direct search, not assumption:
- No `connector`/`integration` module, route, or model anywhere under `backend/app/`.
- No `IntegrationLink`-style table in `backend/app/models.py` or the migrations.
- No design doc for it under `docs/design/`.
- The only two things the spec's "collect data via API" requirement overlaps with here are the
  **manual** xls/xlsx catalog upload (`import_routes.py`, built and tested) and the invented
  generic-HTTP stubs for **SMS** and **email** sending (`app/sms.py`, `app/email.py`) — neither of
  which is the LMS/CMS integration; both are one-way outbound notification channels, unrelated to
  pulling interaction data from an external LMS/CMS.

**Finding — a real mock already exists, but on a different, unmerged branch.** The sibling git
worktree `.worktrees/ai-integration-candidate` (branch `ai/integration-candidate`, diverged from
this branch's common ancestor, never reconciled back — the same kind of unreconciled history
already noted for `ai/auth-registration`/`ai/registration-polish` in this branch's own D-158) has
a complete, tested, documented **bidirectional mock LMS/CMS connector**:
- `backend/app/connectors.py` — wire-format-agnostic idempotent create-or-update logic
  (`apply_interaction`, keyed on `(source, external_id)`), and an outbound "current state" shaper.
- `backend/app/connector_routes.py` — the actual `POST/GET /api/v1/integrations/{lms|cms}/...`
  endpoints: parses the mock's invented JSON shape, resolves university/status names to CRM rows,
  shapes the response.
- `backend/migrations/versions/0013_integration_links.py` — the `integration_links` table.
- `docs/api/integrations.md` and `docs/decisions.md` D-184–D-187 on that branch — the mock's
  contract is fully documented, labelled a mock in its own first line, and states explicitly:
  *"replacing it with the real contract only requires rewriting the parsing/response-shaping
  layer (`connector_routes.py`), not the CRM business logic (`connectors.py`)."*
- Shared-secret auth (`X-Connector-Key`), per-connector audit events, and a real test suite
  (`backend/tests/test_connectors.py`).

**This is a clear, well-isolated replacement point** — exactly what task item 2 asked me to check
for — but it is not reachable from `ai/phone-verification` today. Whoever continues this work
should decide whether to port/merge that connector code onto this branch (recommended: it already
satisfies D-008 and is tested) or rebuild it fresh here.

**Unknown fields and scenarios — not invented, listed as genuinely unknown** (per the instruction
not to make up a contract): the mock's field names, auth scheme, and direction are all guesses
made in the absence of the real spec. Specifically unknown until the case owner provides it:
- Real base URL(s)/host for the LMS and for the Laravel CMS website.
- Real authentication scheme (API key, OAuth2 client-credentials, mutual TLS, a Rostelecom SSO
  token — the mock guessed a shared header secret).
- Real field names/types for an interaction/course/student record (the mock invented
  `external_id`, `university`, `program`, `product`, `status`, `responsible`, `students`,
  `deadline` — none of these are confirmed real field names).
- Direction: whether the real systems push to the CRM (webhook), the CRM polls them, or both — the
  spec only says "use the API to collect information," which does not settle this. The mock
  supports both directions as a hedge, not because the real direction is known.
- Real status vocabulary used by the LMS/CMS, and whether it maps 1:1 onto the CRM's 14-step
  workflow or needs an explicit translation table.
- Conflict rule: if both the LMS/CMS and a CRM user edit the same interaction, whose write wins —
  not specified anywhere in the brief.
- Whether the integration may create new universities/programs/products, or only match against
  the existing catalog (the mock assumes match-only; not confirmed).
- Rate limits, retry/backoff, and idempotency-key conventions the real systems might require.

## 4. Interface design — flagged separately (task item 3)

Recorded as its own item, not merged into the Rostelecom item above: **the interface design needs
a general improvement pass** — visual density and spacing/margin consistency across pages. This
session's redesign of the Задачи page (removing the page-wide eyebrow/subtitle clutter, enlarging
the primary view/scope tabs, shrinking and right-aligning the counters/«Шаблоны планов» row) is one
data point that the same kind of crowding likely exists on other pages and was never audited
end-to-end. Concretely still needed: re-check tab/row/button sizes and margins on the Задачи page
itself across viewport widths (only checked at the widths exercised by the automated tests and one
manual build check — no dedicated cross-viewport visual regression pass was run), and a similar
pass over the other pages (Договоры, Взаимодействия, Справочники, Аналитика, Настройки pages) that
were never part of a dedicated design review.

## 5. Everything flagged is now durably tracked

Added to `docs/decisions.md`, new "Flagged follow-up work" section:

- **F-001** — Rostelecom LMS/CMS integration, marked **IMPORTANT**, status "not started on this
  branch (built elsewhere, unmerged)."
- **F-002** — general interface-design polish pass, including the Задачи page size/margin
  re-check, marked **Design** priority, status "not started."

## 6. What's blocked, and why

- **Rostelecom LMS/CMS integration**: blocked on the case owner providing the real API contract
  (per the specification's own words). Not blocked on effort — a working mock with a clean
  replacement seam already exists (see §3), just on a different branch.
- **Real SMS provider** (`app/sms.py`) and **real email provider** (`app/email.py`): both are
  generic, invented HTTP contracts (D-157, D-210) — blocked on the case owner supplying the actual
  gateway's/provider's documented API before either can be pointed at anything real.
- Remaining **Настройки** sections not yet built this stage: Организация, Безопасность,
  Резервное копирование, Уведомления (the last of these also needs its own scheduler
  infrastructure, per the owner's "keep infrastructure changes separated" instruction). Not
  blocked on anything external — just not yet scheduled.

## 7. Known issues

- The FK-cycle warning between `email_sender_identities` and `users` in Alembic's table-sort logic
  is cosmetic (confirmed via `alembic check` passing in the same run) but still prints on every
  migration run — noted, not fixed, low priority.
- `KeycloakAdminClient.list_users()` is not paginated beyond its default 200-row page in
  `GET /admin/pending-registrations` (D-215) — fine for the realm's current size, would need
  paging if the realm grows past ~200 accounts.
- The interface-design gap described in §4 — not a defect in any one feature, a cross-cutting
  polish gap.

## 8. Results of the checks actually run

- Backend test suite: **run**, 384 passed, 0 failed.
- Frontend test suite: **run**, 270 passed, 0 failed; ESLint: **run**, clean; `tsc --noEmit`:
  **run**, clean; production build: **run**, succeeds.
- Live-site smoke check: **run**, `/api/v1/health` and `/` both return 200, all six Compose
  services report healthy.
- Rostelecom LMS/CMS integration presence check: **run** (grep across `backend/app/`,
  `docs/design/`, and the sibling worktree) — see §3 for the full finding.
- NOT run this pass, explicitly: a cross-viewport/browser visual check of the Задачи redesign (no
  browser automation was used this session to look at rendered pixels beyond what the build itself
  proves); a full re-audit of every other page's spacing (§4 is a flag to do this, not a completed
  audit); no attempt was made to reconcile or merge the `ai/integration-candidate` branch's
  connector work onto this branch — that is a decision for whoever continues this, not made here.

## 9. Specific next steps, suggested order

1. Decide whether to port the `ai/integration-candidate` branch's mock LMS/CMS connector onto
   `ai/phone-verification`, or leave the two branches separate and build a fresh mock here — either
   way, get the owner's confirmation of the connector's guessed contract details in §3 before
   investing further, since several of them are unverified assumptions.
2. Run a dedicated interface-design pass (F-002): audit spacing/margins across pages, not just
   Задачи.
3. Continue the remaining Настройки sections (Организация, Безопасность, Резервное копирование,
   Уведомления + scheduler), each as its own reviewed slice, per this project's established
   process.
4. When the case owner supplies the real LMS/CMS/SMS/email provider contracts, replace the
   corresponding mock/stub layer only (the isolation described in §3 and in `app/sms.py`/
   `app/email.py`'s own docstrings already exists specifically so this swap doesn't touch business
   logic).
