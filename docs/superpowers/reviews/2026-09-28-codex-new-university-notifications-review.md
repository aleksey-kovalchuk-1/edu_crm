# Task 4 — Codex review: new-university notifications and the access-request design

Scope: `codex/new-university-notifications` — `2754354` (in-app «Создали новый вуз») and `99c5f04` (design doc only).
Nothing in Codex's worktree or branch was changed. Tests ran from separate detached copies.

## What was checked
- Full backend suite on Codex's commit: **694/694 pass**.
- Codex's changes applied (uncommitted) onto today's main `3a2c7ce`: merges cleanly; backend **697/697**, frontend **459/459**.
- A throwaway probe test (deleted afterwards) for catalogue imports.
- Production, read-only: Keycloak realm flags and SMTP presence, API email settings (key names only).

## 2754354 — «Создали новый вуз»
Works as described: every active KAM (`crm-user`) except the author gets one notification per new university,
it respects the per-event switch and pause, a rollback leaves nothing, and duplicates are prevented by a dedupe key.
Users who cannot open the university see the name without a link.

Findings:
1. **Important — catalogue imports flood the bell.** `import_routes.py` creates universities through the same flush,
   and only contracts are silenced for imports (`notification_source == 'import'`). Probe: one import with one new
   university and 3 KAMs → 3 notifications; an import of 200 new universities with 10 KAMs would create 2,000.
   Fix: skip `university_created` when `db.info['notification_source'] == 'import'` (one line, plus a test), or send
   one summary notice per import.
2. **Product question — KAMs are told about universities they can't open.** API-created universities default to
   `team_visible_to_managers = False`, so most KAMs get a name they cannot click. Either notify only users who can see
   the university (drop it from `UNSCOPED_EVENTS`), or confirm the name-only announcement is wanted.
3. Supervisors, admins and the superadmin never get it (recipients are `crm-user` only). Matches the doc; confirm.
4. The partner sync script (`sync_partner_universities.py`) also triggers it, with no author. Fine for real use; note
   it for demo resets.
5. No frontend change needed: the toggle appears in «Уведомления» automatically; link-less items already render.

## 99c5f04 — access-request design (document only)
The idea is sound (no account until the superadmin approves, no account-existence leaks, dedupe, retries), but it
does not match what is live:

1. **Critical, already live: sign-up can't be finished on production.** Keycloak has `registrationAllowed = true` and
   `verifyEmail = true` but **no SMTP server**, so the confirmation email is never sent and a new user is stuck at
   «Подтвердите e-mail». «Забыли пароль» can't send either. (This is why the test accounts needed `emailVerified`.)
2. **Critical: the app cannot send any email in production.** `api.env` has no `EMAIL_*` settings, so `send_email`
   only writes to the log. The design's acknowledgement email would never arrive. `email.py`'s HTTP contract is
   invented, not a real provider's API. A real provider (or SMTP) and credentials are needed first.
3. **Two parallel queues.** Main already has «Настройки → Пользователи и роли → Заявки на доступ»: people who signed up
   in Keycloak wait there until the superadmin grants a role. The design adds a second queue (`access_requests`) and
   says "do not enable unrestricted Keycloak self-registration" — but self-registration is on in production. One
   path has to be chosen:
   - A. Keep Keycloak sign-up (add SMTP, fix the theme — Task 2), add the in-app superadmin notification and the
     acknowledgement email to the existing queue. Smallest change.
   - B. Codex's design: turn Keycloak sign-up off, add the request form and new queue.
4. The notification model only allows links to university/launch/task/contract and filters by university scope; a
   superadmin-only «Новая заявка на доступ» needs a new link type and visibility rule (the design mentions the event
   but not these).
5. The applicant message hard-codes the administrator's personal address; make it an organisation
   setting.
6. The design drops CAPTCHA, but reCAPTCHA keys already exist for the Keycloak sign-up; a public unauthenticated form
   with only rate limits invites spam.
7. There is no rate-limit helper in main yet; it has to be built (the design assumes "basic IP and email limits").

## Owner decisions (2026-09-28)

- Path **A**: sign-up stays in Keycloak. The access-request form from `99c5f04` is not built. The superadmin
  notification and the acknowledgement e-mail were added to the existing queue instead (worktree
  `.worktrees/login-registration`, D-239).
- Mail: Russian providers only (Russian SMTP mailbox for the API and Keycloak).
- СПбПУ's address: spbu@spbu.ru.
- KAMs keep the «Создали новый вуз» announcement for universities they can't open (finding 2 stands as designed).
- Still open for Codex's commit: the catalogue-import flood (finding 1).

## Suggested next steps (as written before the decisions)
- Choose A or B (item 3). My recommendation: **A**, because the queue, roles and CAPTCHA already exist and only
  email delivery and the notification are missing.
- Either way, configure a real mail provider for Keycloak (SMTP) and for the API first.
- Before merging Codex's commit: fix the import flood (finding 1) and decide finding 2.
