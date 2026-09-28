# UniCRM — improvement todo list

Working list, ordered by priority within each section. Started 2026-09-24 after the design-token
and Задачи-list redesign (D-216, D-217), which are live on unicrm.tech. Details and history live in
`docs/decisions.md` (D-/F- items), `docs/night-backlog.md` (T- items) and
`docs/improvement-ideas.md` (I- items); this file is the single place to see what is next.

Legend: `[ ]` open · `[~]` in progress · `[x]` done.

## 0. Housekeeping (do first)

- [x] Push `ai/design-tokens` (pushed 2026-09-24).
- [ ] Open a PR into `main` once `ai/phone-verification` (its base) is merged.
- [ ] Reconcile the branch history: `ai/phone-verification`, `ai/auth-registration`,
      `ai/registration-polish`, `ai/integration-candidate` all diverge from `main` (D-158). Decide
      the merge order, merge, delete stale branches/worktrees.
- [ ] Protect `main` (P-003) so the live site is only ever deployed from reviewed code.
- [x] Write a one-command deploy script (`scripts/deploy-public.sh`: encrypted database and
      attachment backups → rebuild api/web with both compose files → health + login redirect).
- [x] Activate the customer's ten named universities and deactivate the six demonstration rows
      without deleting linked task and interaction history. New universities remain addable in Settings.
- [ ] Add `CLAUDE.md` (stack, commands, conventions, "the laptop stack *is* production").

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
- [ ] Email delivery of notifications needs a configured provider; production currently uses log-only delivery.
- [x] Fill Настройки → Организация and Резервное копирование (status of complete encrypted pairs).
- [ ] Optional manual backup trigger from the web UI; retain host-side execution and no recovery key in API.
- [ ] Data scopes admin screen; supervisor reassigns responsible people (T-025).
- [x] JSON export of full interaction reports (T-034): same filters/columns, server-side scope and audit.
- [x] Create manager and administrator accounts from Пользователи и роли (superadmin only).
- [x] Change an existing user's manager/administrator role and assign either role to a pending
      registration from Пользователи и роли (superadmin only; supervisor/superadmin protected).
- [x] Reset an existing or pending user's temporary password from Безопасность (superadmin only).

## 3. Integrations

- [x] Record the owner's permanent-mock decision for LMS and the website
      (`docs/design/lms-cms-mocks.md`, 2026-09-28). No real API connector is planned.
- [ ] Implement **permanent, labelled LMS and website stubs** from versioned synthetic fixtures;
      keep their data out of confirmed reports, test permissions and repeat handling. The
      divergent `ai/integration-candidate` must not be deployed as a real connector.
- [ ] Real SMS and email providers behind the existing injectable senders (D-157, D-210).
- [ ] Superset profile on the current schema, read-only analytics views (T-074).

## 4. Quality, security, operations

- [ ] Security headers: CSP, `Referrer-Policy`, `Permissions-Policy`, HSTS on the public nginx
      config (only `X-Content-Type-Options` today) (T-070).
- [ ] Login rate limiting; clean up abandoned `login_states` rows (I-009).
- [x] Automatic daily encrypted database + attachments backup on the production Mac, 30-day
      retention with seven complete days kept, and a tested restore (2026-09-27).
- [ ] Uptime check for unicrm.tech (the site depends on this laptop being awake and online).
- [ ] Load test: 50 concurrent users, 10 parallel reports (T-071).
- [ ] Test-client deprecation warnings (I-005); pin local Python to 3.12 like Docker/CI (I-006).
- [ ] Code-split the frontend bundle (Vite warns about chunk size).
- [ ] User and admin guides in the app (T-072); architecture and install docs (T-073).

## Handover — state on 2026-09-25

Live on unicrm.tech and pushed to `ai/design-tokens` (not yet merged into `main`):
design tokens (D-216), Задачи list (D-217), task page (D-218), board cards (D-219), compact shell
and density pass (D-220), reports module (D-221), chart PNG/PDF export (D-222).

**Next, in order**
1. Calendar view for tasks — a fourth «Календарь» tab next to Список/Сроки/Мой план: month grid
   by `deadline` (and `planned_start` when set), same scope/filters as the list, drag to move a
   deadline via the existing `PATCH /tasks/{id}` (as «Сроки» does, D-206). Frontend only.
2. Owner: fill the IT product / direction catalogs and link interactions (reports filters by
   product/direction match nothing until then). Do not seed placeholder catalog data.
3. Housekeeping section above: PR into `main` after `ai/phone-verification` is merged, protect
   `main`, `scripts/deploy-public.sh`, `CLAUDE.md`.
4. Then: slide-over task panel, permanent LMS/website stubs, security headers.

**How to deploy** (the laptop stack *is* production): `scripts/deploy-public.sh <label>` makes
encrypted database and attachment copies, updates API/web/notifier, and checks local/public health
and the login redirect. Existing Keycloak realms additionally need the idempotent middle-name and
login-event setup scripts when the Settings features are first released.
