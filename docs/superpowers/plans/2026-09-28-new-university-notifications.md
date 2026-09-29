# New University Notifications Implementation Plan

> **For agentic workers:** Native execution in this session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify every other active CRM manager in the site bell when a university is created, while respecting existing university access rules.

**Architecture:** Extend the existing in-app notification event catalog and SQLAlchemy change collector. Add no email, SMS, browser push, or database schema; the preferences UI renders event groups and labels returned by the API, so adding a backend event automatically adds its setting.

**Tech Stack:** Python, FastAPI, SQLAlchemy, PostgreSQL, pytest, React settings UI (existing dynamic preferences).

**Spec:** `docs/superpowers/specs/2026-09-27-notifications-design.md` plus the user's approved “ТЗ: уведомления в UniCRM” in this task.

## Global Constraints

- Notifications are delivered only in the UniCRM site bell.
- The creator does not receive a notification about their own action.
- Recipients must be active managers with `crm-user`; managers without university access see the short announcement without a link.
- Do not expand access to existing university-scoped data such as contacts, contracts, reports, or tasks.
- Respect per-event preferences and global notification pauses; do not queue notifications for later.
- One creation yields at most one notification per recipient, even if processed more than once.
- Notification creation shares the university creation transaction; rollback leaves no notification.
- Existing notification behavior must remain intact.

## Review Focus

- A manager outside the university scope must still see the announcement but receive no link or access to university-scoped data; keep the creator excluded.
- A manager account with additional roles still receives only one notification; exclude inactive and non-manager accounts.
- A disabled preference, active pause, duplicate event, update, and rollback must not create an unintended notification.
- Event catalogue labels/defaults and API preferences must stay in sync; no email sender may be invoked.
- Existing university assignment and visibility rules for previously created universities must not change.

---

### Task 1: Notify managers about a newly created university

**Files:**
- Modify: `backend/app/notifications.py`
- Modify: `backend/app/notification_events.py`
- Modify: `backend/app/notification_routes.py`
- Modify: `docs/superpowers/specs/2026-09-27-notifications-design.md`
- Modify: `docs/api/notifications.md`
- Test: `backend/tests/test_notifications_core.py`
- Test: `backend/tests/test_notification_events.py`

**Interfaces:**
- Consumes: `notify(...)`, existing `EVENT_TYPES`, `GROUPS`, `UNSCOPED_EVENTS`, `User.roles`, SQLAlchemy session hooks.
- Produces: event key `university_created`, label `Создали новый вуз`, group `universities`, enabled by default; notification links to `university/{id}` only while the recipient has access.

- [x] **Step 1: Add failing tests**
  - Assert the catalogue contains 21 events and `university_created` is enabled by default.
  - Create a university as a non-manager administrator; assert all active `crm-user` accounts except the creator receive one notification, and supervisor/admin-only and inactive users receive none.
  - Assert a manager-created university remains outside other managers' scope; they receive the announcement without a link. After assignment, the link should become available.
  - Assert preference disabled, pause active, update, duplicate handling, and rollback suppress or avoid extra notifications.

- [x] **Step 2: Run the targeted tests and confirm expected failures**
  - Run from `backend`: `pytest tests/test_notifications_core.py tests/test_notification_events.py -q`.

- [x] **Step 3: Implement event and recipient handling**
  - Add `university_created` to the existing group catalog, enabled by default.
  - Track newly flushed `University` rows and snapshot their id.
  - In the existing university event handler, query active users whose role array contains `crm-user`; call `notify` excluding the actor, linking the university, and using persistent dedupe key `university_created:{id}`.
  - Add `university_created` to `UNSCOPED_EVENTS` so all managers see the short announcement; the existing API link visibility check must return `null` to recipients without access. Keep university scope and assignments unchanged.

- [x] **Step 4: Verify targeted and full backend suites**
  - Re-run the targeted tests, then the repository's full backend test command.
  - Confirm the settings API returns the new event in the universities group; the current frontend should render it without a code change.

- [x] **Step 5: Update docs and review the diff**
  - Update the notification event matrix, recipient/access rules, default preference, and API documentation.
  - Inspect the complete diff for unintended changes to existing access rules and confirm there is no mail/SMS/push call.

- [x] **Step 6: Commit the completed local change**
  - Run `git diff --check` and confirm only the event implementation, tests, and notification docs are changed.
  - Commit in this worktree with message `feat: notify managers about new universities`.
