# UniCRM — improvement todo list

Working list, ordered by priority within each section. Started 2026-09-24 after the design-token
and Задачи-list redesign (D-216, D-217), which are live on unicrm.tech. Details and history live in
`docs/decisions.md` (D-/F- items), `docs/night-backlog.md` (T- items) and
`docs/improvement-ideas.md` (I- items); this file is the single place to see what is next.

Legend: `[ ]` open · `[~]` in progress · `[x]` done.

## 0. Housekeeping (do first)

- [x] Push `ai/design-tokens` (pushed 2026-09-24).
- [x] `ai/phone-verification` and `ai/design-tokens` are merged into `main`; work since then goes through PRs.
- [ ] Old branches still diverge from `main` (state 2026-09-29): `ai/auth-registration` (3 commits),
      `ai/registration-polish` (4), `ai/integration-candidate` (19 — invented contract and shared secret,
      must never be merged, D-246). Decide whether to delete them; the local worktrees were removed.
- [ ] Protect `main` (P-003) so the live site is only ever deployed from reviewed code.
- [x] Write a one-command deploy script (`scripts/deploy-public.sh`: encrypted database and
      attachment backups → rebuild api/web with both compose files → health + login redirect).
- [x] Activate the customer's ten named universities and deactivate the six demonstration rows
      without deleting linked task and interaction history. New universities remain addable in Settings.
- [x] Add `CLAUDE.md` (stack, commands, conventions, "the laptop stack *is* production").

## 1. Design and UX (F-002)

- [x] Design tokens, type scale ≥ 11px, WCAG AA text contrast (D-216).
- [x] Задачи «Список»: one toolbar row, counter chips, header sorting, richer rows, assignee /
      creator filters, quick-add (D-217).
- [x] **Task detail page** (D-218) — two columns (content left; status, deadline, people, links in a
      right sidebar), inline editing instead of the separate «Изменить» form, primary status
      action as a big button. Fixes the fields sitting flush against the panel edge. History stays
      a separate panel right after the title block (owner decision D-198).
- [ ] Edit co-executors and observers from the task sidebar (read-only today).
- [ ] Open a task in a slide-over panel from the list (keeps the list context, Bitrix24 "slider").
- [x] Boards («Сроки», «Мой план») (D-219): compact cards — title, deadline pill, avatars, institution tag,
      progress; move ↑/↓ and «Переместить» into a "⋯" menu (keyboard access stays).
- [ ] Calendar view for tasks (`planned_start` / `deadline` already exist).
- [x] Page headings (D-220): drop the marketing slogans («Всё важное — в одном месте»), one compact heading
      row with actions; remove the duplicate breadcrumb.
- [ ] Top bar: global search, notification bell, global «+ Создать».
- [x] Sidebar: dead workspace switcher removed (D-220).
- [x] Sidebar and footer: show demo disclaimers only in demo builds, not on unicrm.tech.
- [x] Density pass (D-220): Учебные заведения as a table, Договоры filters behind «Фильтры»,
      no page scrolls sideways on phones.
- [ ] Dark theme (a second set of token values).
- [ ] Mobile and accessibility audit (T-076): keyboard paths, focus order, screen-reader labels.

## 2. Product features

- [x] **Reports module** (D-221): «Отчёты» page — period, universities, directions, products,
      responsible, status, selectable columns; preview; xlsx / xls / pdf (Cyrillic) downloads;
      audited; 10 parallel builds tested. Interactions can link to a catalog IT product.
- [ ] Link the existing interactions to catalog IT products (the live catalog is empty — fill
      Справочники or import them first); until then product/direction filters match nothing.
- [x] Charts export to PNG / PDF (D-222): Аналитика and Обзор charts.
- [x] In-app notification centre and Настройки → Уведомления, including the date-based scheduler.
- [x] Email delivery through the Russian SMTP mailbox (Yandex, D-238/D-240); Keycloak mail uses the same box.
- [x] Fill Настройки → Организация and Резервное копирование (status of complete encrypted pairs).
- [x] Manual backup trigger from the web UI; execution remains on the host, with no recovery key in API.
- [ ] Data scopes admin screen; supervisor reassigns responsible people (T-025).
- [x] JSON export of full interaction reports (T-034): same filters/columns, server-side scope and audit.
- [x] Create manager and administrator accounts from Пользователи и роли (superadmin only).
- [x] Change an existing user's manager/administrator role and assign either role to a pending
      registration from Пользователи и роли (superadmin only; supervisor/superadmin protected).
- [x] Reset an existing or pending user's temporary password from Безопасность (superadmin only).

## 3. Integrations

- [x] Record the owner's permanent-mock decision for LMS and the website
      (`docs/design/lms-cms-mocks.md`, 2026-09-28). No real API connector is planned.
- [x] Minimal LMS/website boundary instead of user-facing stubs (D-246): preliminary internal format,
      `GET /api/v1/integrations/contracts`, POST placeholders that store nothing. No screens.
- [ ] When the customer's LMS/website contracts and samples arrive: replace the preliminary adapters in
      `backend/app/integrations/`, version the format, record a decision (D-233 until then).
- [x] Customer files in «Загрузка справочников» (D-247): applications JSON (number, course, stream only)
      and the RTK workbook by sheet name; «Руководитель» only.
- [ ] Vendors file (`Вендоры.xlsx`: Компания, Продукт, ФИО, Телефон, Почта, Способ связи) — postponed by the
      owner; first decide whether contacts' personal data is imported or only companies and products.
- [ ] Real SMS provider behind the existing injectable sender (D-157, D-210); email is done (D-238).
- [ ] Superset profile on the current schema, read-only analytics views (T-074).

## 4. Quality, security, operations

- [ ] Security headers: CSP, `Referrer-Policy`, `Permissions-Policy`, HSTS on the public nginx
      config (only `X-Content-Type-Options` today) (T-070).
- [ ] Login rate limiting; clean up abandoned `login_states` rows (I-009).
- [x] Automatic daily encrypted database + attachments backup on the production Mac, 30-day
      retention with seven complete days kept, and a tested restore (2026-09-27).
- [ ] Uptime check for unicrm.tech (the site depends on this laptop being awake and online).
- [ ] Off-laptop copies of the recovery key, `deploy/local/`, `~/.cloudflared/` and the backup folder —
      today they exist only on the production Mac (owner action).
- [x] Deploy backups verified with `scripts/verify-encrypted-pair.sh` (2026-09-29: pairs
      `deploy-20260929-143853` and `deploy-20260929-145440` decrypt and parse).
- [ ] Load test: 50 concurrent users, 10 parallel reports (T-071).
- [ ] Test-client deprecation warnings (I-005); pin local Python to 3.12 like Docker/CI (I-006).
- [ ] Code-split the frontend bundle (Vite warns about chunk size).
- [ ] User and admin guides in the app (T-072); architecture and install docs (T-073).

## Handover — state on 2026-09-29

Production (unicrm.tech) runs `main` at the latest deployed merge; everything is on GitHub and
`docs/REVIEW.md` is the reviewer entry point. Recent decisions: D-243…D-247.

**Next, in order**
1. Owner: off-laptop copies of the recovery key, `deploy/local/`, `~/.cloudflared/`, backups; protect `main` (P-003).
2. Security headers on the public nginx (T-070), uptime check.
3. Vendors file importer once the contact-data decision is made.
4. Product backlog: calendar view for tasks, slide-over task panel, dark theme, accessibility audit.

**How to deploy** (the laptop stack *is* production): merge the PR, `git merge --ff-only origin/main` in
the main checkout, tag rollback images (`docker image tag "edu-crm-${i}" "edu-crm-${i}:rollback-<sha>"`), then
`bash scripts/deploy-public.sh` — it makes encrypted database and attachment backups first, releases
API/notifier/web, runs migrations on API start and checks local and public health.
