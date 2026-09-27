# Analytics Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy annual analytics page with three scoped interaction charts and one matching PDF.

**Architecture:** A single backend snapshot builder reads scoped interaction history and returns all chart series. JSON and ReportLab PDF routes call that builder with the same filters. The React page owns only date and university selections, chart rendering, and the visible browser-time-zone fallback.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, ReportLab, React, TanStack Query, Vitest, pytest.

**Spec:** `docs/design/analytics-interactions-2026-09-27.md`

## Global Constraints

- Do not edit the Settings or profile UI files being changed concurrently by Claude.
- Do not push or deploy without the user's approval.
- Do not synthesize implementation dates or student counts.
- Use `workflows.STAGE_GROUPS` and `stage_group`, and use `university_scope` on every data query.
- Preserve Russian labels and embedded Cyrillic fonts in PDF.

## Review Focus

- An initial imported status in «Обучение» is not an implementation; test excludes it.
- Multiple interactions from one university count once in each funnel step; test deduplicates.
- An event near midnight can belong to a different local month; test `Asia/Tokyo` conversion.
- A selected university outside the manager's scope must not appear in JSON or PDF; test rejects it.
- A period with no implementations must show an empty state, while gaps between implementations show zero; test both.

---

### Task 1: Calculation rules

**Files:**
- Create/modify: `backend/app/analytics_metrics.py`
- Test: `backend/tests/test_analytics_metrics.py`

**Interfaces:**
- Consumes: status positions, UTC `StatusChange.created_at`, `STAGE_GROUPS`.
- Produces: `first_implementation_at(changes)`, `monthly_implementations(events, period_from, period_to, time_zone)`, `funnel_counts(university_stage_groups)`, `top_universities(implemented_rows)`.

- [x] Write failing tests for first genuine transition into training and for month grouping.
- [x] Run them red, implement the two functions, run them green.
- [x] Write failing tests with two interactions for one university, stage counts `[2, 2, 1, 0, 0]`, and six universities sorted by programs, students, name.
- [x] Implement `funnel_counts` and `top_universities`; run the focused tests green.
- [x] Run the backend suite and commit this unit with its tests.

### Task 2: Scoped snapshot API

**Files:**
- Create: `backend/app/analytics_routes.py`
- Modify: `backend/app/main.py` (router registration only)
- Test: `backend/tests/test_analytics_routes.py`

**Interfaces:**
- Consumes: period dates, repeated `university_id`, IANA time-zone name, `university_scope`, Task 1 metrics.
- Produces: `GET /api/v1/analytics/interactions`, `analytics_snapshot(db, user, filters)` for the PDF route.

- [x] Write failing API tests: `period_from > period_to` returns 422; inaccessible selected university returns 404; manager response excludes out-of-scope university/events; one period-boundary event and one genuine training transition produce the expected series.
- [x] Implement typed query filters and validate the time-zone name with `ZoneInfo` and date order before querying.
- [x] Build the scoped `Launch`/`University`/`StatusChange` snapshot, using event local dates for the funnel and first genuine training transition for month/rank data.
- [x] Run focused and full backend tests; commit the scoped API.

### Task 3: Replace page content

**Files:**
- Create: `frontend/src/api/analytics.ts`, chart components under `frontend/src/components/analytics/`
- Replace: `frontend/src/pages/AnalyticsPage.tsx`
- Modify: `frontend/src/app/navigation.ts` (analytics subtitle/action), existing analytics expectations in `frontend/src/app/App.test.tsx` and `frontend/src/pages/reports.test.tsx`
- Test: `frontend/src/pages/analytics.test.tsx`

**Interfaces:**
- Consumes: snapshot JSON from Task 2 and scoped `useUniversities()` options.
- Produces: four ordered blocks, date and multi-university filter, visible browser-time-zone note, accessible SVG/HTML chart labels, PDF URL with exactly the active filters.

- [x] Write failing UI tests for block order, default current-year period, multi-select affecting the API query, clear inverted-period error, chart empty states, and exact PDF URL.
- [x] Implement a single analytics query hook and replace the legacy annual content; leave Overview's existing chart alone.
- [x] Render horizontal funnel bars, a month line with zero gaps, and paired top-five columns with numeric labels; use the design system and responsive layout.
- [x] Update tests that referred to the removed annual analytics chart, then run all frontend tests, lint and production build; commit the page.

### Task 4: Matching PDF

**Files:**
- Modify: `backend/app/analytics_routes.py`
- Test: `backend/tests/test_analytics_routes.py`
- Document: `docs/api/analytics.md`

**Interfaces:**
- Consumes: `analytics_snapshot` from Task 2.
- Produces: `GET /api/v1/analytics/interactions.pdf`, vector charts in a downloadable PDF with the same values and scoped labels as JSON.

- [x] Write failing tests for PDF auth/scope, filter and date parity with JSON, all three chart titles/values, embedded Cyrillic fonts, and period-based filename.
- [x] Implement ReportLab drawing using bundled DejaVu fonts; show the three empty states where appropriate.
- [x] Render a representative PDF to PNG and inspect legibility; run backend suite and frontend suite once more.
- [x] Update API documentation and commit; leave the branch local for user review and deployment approval.
