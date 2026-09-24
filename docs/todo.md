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
- [ ] Write a one-command deploy script (`scripts/deploy-public.sh`: backup → rebuild api/web with
      both compose files → health + login-redirect check), so a deploy can't drop the public
      overlay again.
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
- [ ] Sidebar: show the «Демонстрационный контур» note only in demo mode (needs a demo flag).
- [x] Density pass (D-220): Учебные заведения as a table, Договоры filters behind «Фильтры»,
      no page scrolls sideways on phones.
- [ ] Dark theme (a second set of token values).
- [ ] Mobile and accessibility audit (T-076): keyboard paths, focus order, screen-reader labels.

## 2. Product features

- [ ] **Reports module** (T-050–T-054): filtered report builder (period, universities,
      directions, products, responsible, status, selectable columns), async jobs on the existing
      worker, xlsx / pdf (Cyrillic) export, reports screen. Required by the specification; nothing
      exists yet.
- [ ] Notifications: in-app centre + email for "assigned to you", "overdue", "new comment",
      "review requested"; Настройки → Уведомления (currently a placeholder) becomes their settings.
- [ ] Fill the other placeholder settings pages: Организация, Безопасность, Резервное
      копирование (show the backups `scripts/db-backup.sh` already makes).
- [ ] Data scopes admin screen; supervisor reassigns responsible people (T-025).
- [ ] JSON export of results (T-034).
- [ ] Promote users to supervisor/admin from Пользователи и роли (currently only first approval).

## 3. Integrations

- [ ] **Rostelecom LMS + Laravel CMS connector (F-001, IMPORTANT)** — port the tested mock
      connector from `ai/integration-candidate` (`connectors.py`, `connector_routes.py`, migration
      `integration_links`, `docs/api/integrations.md`); swap in the real contract when the case
      owner provides it (open questions listed in the 2026-09-22 handover report §3).
- [ ] Real SMS and email providers behind the existing injectable senders (D-157, D-210).
- [ ] Superset profile on the current schema, read-only analytics views (T-074).

## 4. Quality, security, operations

- [ ] Security headers: CSP, `Referrer-Policy`, `Permissions-Policy`, HSTS on the public nginx
      config (only `X-Content-Type-Options` today) (T-070).
- [ ] Login rate limiting; clean up abandoned `login_states` rows (I-009).
- [ ] Automatic daily database + attachments backup with retention, and a tested restore
      (scripts exist; nothing schedules them).
- [ ] Uptime check for unicrm.tech (the site depends on this laptop being awake and online).
- [ ] Load test: 50 concurrent users, 10 parallel reports (T-071).
- [ ] Test-client deprecation warnings (I-005); pin local Python to 3.12 like Docker/CI (I-006).
- [ ] Code-split the frontend bundle (Vite warns about chunk size).
- [ ] User and admin guides in the app (T-072); architecture and install docs (T-073).
