# UniCRM redesign on the Rostelecom design system — design system

Status: **for owner review.** Approved so far (28 Sep 2026): visual direction «A, рабочий реестр» in Rostelecom Purple light; licence in place; no `@atomaro/*` packages (no registry token); Rostelecom Basis may be shipped. The mockups are illustrations, not a functional specification. Implementation starts only after the owner approves this document and the plan `docs/superpowers/plans/2026-09-28-rostelecom-redesign.md`.

Audit, sources and mockups: the shared doc «UniCRM interface audit and Rostelecom design system proposal».

## 1. Principles

1. **A working register.** Hierarchy comes from type, alignment, spacing and dividers. Tables, filters, statuses and the next action come before decoration. Page sections are separated by dividers, not wrapped in cards.
2. **Same product, new look.** Every workflow, role rule, server check, calculation, export and authentication step stays as it is. The redesign adds no features and removes none. Ideas for new features go to a separate list for the owner.
3. **Tokens only.** Every colour, size, radius, shadow and duration comes from a token. Token names and values are the Rostelecom Gen2 (Atomaro) Purple light theme, reproduced in UniCRM's own CSS.
4. **Readable and reachable.** Routine information is at least 14 px; body text is 16 px; controls people tap are at least 44×44 px on phones; nothing depends on colour alone.
5. **Honest data.** Demonstration figures are labelled «Демонстрационные данные». The LMS and website APIs are permanent mocks; the interface never implies a live integration.

## 2. Tokens

Source: CSS variables of `.Theme_root_rtk_purple_light` in the Rostelecom React Storybook (Design Tokens stories), read on 28 Sep 2026. Names keep the `--atmr-` prefix so they can be compared with the Storybook one to one. UniCRM's own additions use `--crm-`.

### 2.1 Colour

| Token | Value | Use |
| --- | --- | --- |
| `--atmr-bg-page`, `--atmr-bg-surface1` | `#fff` | Page, content, tables |
| `--atmr-bg-surface2` | `#f9f9fa` | Side menu, table header, filter bar |
| `--atmr-bg-surface3` | `#f4f4f5` | Bar-chart tracks, sign-in background |
| `--atmr-bg-surface4` | `#e8e8ee` | Pressed neutral surfaces |
| `--atmr-fg-default` | `#101828` | All working text |
| `--atmr-fg-soft` | `rgba(16, 24, 40, 0.75)` | Secondary text, captions, table headers |
| `--atmr-fg-muted` | `rgba(16, 24, 40, 0.55)` | Placeholders and disabled hints only |
| `--atmr-border-muted` | `rgba(88, 93, 105, 0.15)` | Row dividers inside tables |
| `--atmr-border-soft` | `rgba(88, 93, 105, 0.25)` | Section dividers, table outline, menu edge |
| `--atmr-border-default` | `rgba(88, 93, 105, 0.5)` | Chart axes |
| `--atmr-accent-default` | `#7700ff` | Primary buttons, links, current menu item text |
| `--atmr-accent-hover` / `--atmr-accent-active` | `#6500d9` / `#5300b3` | Hover and pressed; text on accent containers |
| `--atmr-accent-on-accent` | `#fff` | Text on accent fills |
| `--atmr-accent-container-default` | `rgba(119, 0, 255, 0.1)` | Current menu item, selected chip, secondary button |
| `--atmr-accent-container-soft` | `rgba(119, 0, 255, 0.05)` | Row hover |
| `--atmr-accent-container-hover` | `rgba(119, 0, 255, 0.2)` | Secondary button hover |
| `--atmr-neutral-400` | `#797e8b` | Input borders (override, see 2.5) |
| `--atmr-neutral-500` | `#585d69` | Input border on hover |
| `--atmr-neutral-container-default` / `-hover` | `rgba(88, 93, 105, 0.1)` / `0.2` | Neutral tags, icon-button hover |
| `--atmr-success-default` / `-700` / `-container-default` | `#00ac43` / `#00782f` / `rgba(0, 172, 67, 0.1)` | Fill / text / background |
| `--atmr-warning-default` / `-800` / `-container-default` | `#fda610` / `#98640a` / `rgba(253, 166, 16, 0.1)` | Fill / text / background |
| `--atmr-error-default` / `-700` / `-container-default` | `#ff2626` / `#b31b1b` / `rgba(255, 38, 38, 0.1)` | Fill / text / background |
| `--atmr-info-default` / `-600` / `-container-default` | `#1f69ff` / `#1a59d9` / `rgba(31, 105, 255, 0.1)` | Fill / text / background |
| `--atmr-status-01` … `-06-default` | `#ff4f12`, `#4055e8`, `#038fde`, `#1898a9`, `#ca20d9`, `#d9206f` | Stage dots and chart series, always with a text label |

Status text uses the darker step (`-700`, `-800`, `-600`), never `-default`: each is at least 4.7:1 on white and on its own 10% container.

### 2.2 Typography

Font: **Rostelecom Basis** 400, 500, 700 (`woff2`, 48 KB each), shipped with the app in `frontend/src/assets/fonts/` and with the sign-in theme. Fallback: `Arial, sans-serif`. The Google Fonts import of Manrope is removed.

| Token | Value | Use |
| --- | --- | --- |
| `--atmr-font-heading-h1` | 700 28/32 | Page title |
| `--atmr-font-heading-h2` | 700 22/24 | Section title |
| `--atmr-font-heading-h3` | 700 18/20 | Sub-section, form fieldset, dialog title |
| `--atmr-font-body-m` / `-m-strong` | 400 / 500 16/24 | Body text, form fields, buttons (L) |
| `--atmr-font-body-s` / `-s-strong` | 400 / 500 14/20 | Table cells and headers, labels, menu, buttons (M) |
| `--atmr-font-description-l` / `-l-strong` | 400 / 500 12/16 | Captions, timestamps, menu group labels only |
| Below 768 px | h1 700 22/28 | Page title on phones |

Not used: `description-m` (11 px) and `description-s` (10 px). No text below 12 px anywhere; no routine data below 14 px.

### 2.3 Space, size, shape

- Spacing: `--atmr-spacing-1x` … `-12x` = 4, 8, 12, 16, 20, 24, 32, 40, 48 px (the same 4 px grid as today).
- Control heights: `--atmr-size-m` 36 px (desktop compact), `--atmr-size-l` 48 px (default fields and primary buttons). Every tappable control is at least 44×44 px below 768 px; small visuals (20 px checkbox) get a 44 px hit area.
- Radius: `--atmr-border-radius-m` 8 px (controls), `-l` 12 px (tables, dialogs, drawers), `-full` (chips, tags, counters).
- Border widths: dividers 1 px, inputs 2 px.
- Shadows: `--atmr-shadow-bottom-s` / `-m` only for layers above the page (dropdowns, popovers, drawers, dialogs, the phone menu). Page sections have no shadow.
- Motion: `--atmr-motion-duration-s` 200 ms with `--atmr-motion-easing-productive-standard`; 0 ms under `prefers-reduced-motion: reduce`.
- Breakpoints: `--atmr-breakpoint-s` 768, `-m` 1024, `-l` 1280 px.
- Layers: `--atmr-z-index-dropdown` 1000, `-sticky` 1100, `-overlay` 1300, `-modal` 1500, `-toast` 1600, `-popover` 1700, `-tooltip` 1800.

### 2.4 Mapping from today's tokens

Stage 1 keeps today's token names (`--color-*`, `--text-*`, `--radius-*`, `--shadow-*`, `--sidebar-*`) as aliases pointing at the tokens above, so the whole app changes colour and font at once without touching every rule. Later stages replace alias use rule by rule; the aliases are deleted in Stage 5. `docs/design/tokens.md` is rewritten in Stage 1.

### 2.5 UniCRM overrides (contrast)

| Token | Value | Why |
| --- | --- | --- |
| `--crm-input-border` | `var(--atmr-neutral-400)` | The theme's input border (`border-muted`) is 1.24:1; this is 4.06:1 |
| `--crm-focus-ring` | 2 px solid `--atmr-accent-default`, 2 px offset | The theme's focus colour is 1.13:1; this is 6.5:1 |
| `--crm-overlay` | `rgba(16, 24, 40, 0.5)` | Dialog backdrop |
| Status text | `-700` / `-800` / `-600` steps | The `-default` steps fail as text |

## 3. Layout

### 3.1 Shell

- **Top bar** (64 px, white, divider below, sticky): menu button (below 1280 px), UniCRM wordmark with the organisation name, notifications bell with counter, profile link (initials, name, role) and an always-visible «Выйти» icon button with an accessible name.
- **Side menu** (264 px, `bg-surface2`, divider on the right) scrolls on its own and never hides items off-screen. Below 1280 px it becomes a drawer opened by the menu button (focus moves into it, Esc and navigation close it).
- **Content**: page heading row (h1, one-line context, primary action on the right), then the page. Horizontal padding 32 px (24 px below 1280, 16 px below 768).
- The demo labels («Демонстрационный контур», «Рабочий шаблон · Данные вымышлены») move from the menu bottom and footer to a badge in the top bar and the page footer; both keep their current text and their `VITE_DEMO_MODE` condition.

### 3.2 Menu groups

The menu keeps every current entry, its name, icon, role rule and relative order, and adds group labels:

| Group | Entries (current order) |
| --- | --- |
| Работа | Обзор, Учебные заведения, Договоры, Взаимодействия, Задачи |
| Анализ | Аналитика, Отчёты |
| Данные клиентов | Компании, Слушатели, Заявки на курсы, Загрузка данных, Проверка сигналов |
| Администрирование | Справочники, Загрузка справочников, Процессы, Настройки |

The only order change is that «Справочники» moves from between «Отчёты» and «Компании» to the top of «Администрирование». A group whose entries are all hidden by role is not shown. «Настройки» becomes an expandable group inside the menu (disclosure button, `aria-expanded`), opened by click, tap or keyboard only, and open automatically on settings pages. It replaces the hover flyout, which does not open on touch screens today (a tap fires hover and click, which open and immediately close it).

### 3.3 Pages

- Sections are separated by a 1 px `border-soft` divider and a 24 px gap; section heading h2 with an optional one-line description and a right-aligned link.
- Figures on Overview sit in one divided strip, not separate cards.
- Cards are kept only where the object is a card: board columns (stage board, task board, planner).

## 4. Components

UniCRM builds these itself, following the named Storybook component's look and states.

| Component | Storybook reference | Rules |
| --- | --- | --- |
| Button | Button | Primary (accent fill), secondary (accent container), outline (white, `border-soft`), text, danger (error-700). Sizes L 48 px, M 36 px (44 px below 768). One primary per view. |
| Icon button | IconButton | 48 px (44 px minimum), always an `aria-label`; the `title` attribute is not the only name. |
| Input, select, date, textarea | Input, Select, InputDate, Textarea | Label above (14/20 500), 48 px, 2 px `--crm-input-border`, 8 px radius, focus border accent; hint below (12/16 soft); error below in error-700 with an icon, `aria-invalid` and `aria-describedby`. Dates in ДД.ММ.ГГГГ. Native `<select>` and `<input type="date">` stay native in Stage 2 (restyled), keeping keyboard and screen-reader behaviour. |
| Checkbox, switch | Checkbox, Switch | 20 px box, 44 px hit area, accent fill. |
| Chip (filter toggle) | Chips | 40 px (44 px below 768), `aria-pressed`, count in soft text. |
| Segmented control (view switch) | SegmentedControl | Group of `aria-pressed` buttons; used for «Реестр / Доска», «Список / Сроки / Мой план». |
| Tag (stage, status) | Tags | Neutral container, coloured 8 px dot + text; never colour alone. |
| Badge, counter | Badge, Counter | Menu counters: error container + error-700 text when overdue, neutral otherwise. |
| Inline notification | Notification Inline | Info, success, warning, error; icon + text; used for page errors and the demo notice. |
| Toast | Notification Toast | Short confirmations («Сохранено»); `role="status"`. |
| Table | TableGrid (size M) | 14/20 cells and headers, header on `bg-surface2`, sticky header, row dividers `border-muted`, numbers right-aligned, row hover `accent-container-soft`. Wide tables scroll inside their frame with a visible edge; never the page. Below 768 px the main lists render as stacked rows (title, one secondary line, key values). |
| Pagination | Pagination | 36 px buttons, 44 px below 768. |
| Dialog | Modal | Short confirmations and small forms only; focus trapped, Esc closes, 12 px radius, `--crm-overlay` backdrop. |
| Drawer | Drawer | Filters on phones; the phone menu. |
| Empty state | TableGrid EmptyTable | One sentence of what is missing plus the next action, inside the space the content would take. |
| Loading | Loader | Skeleton rows for tables, spinner elsewhere; no animation under reduced motion. |
| Charts | none (custom SVG/CSS) | Series colours `accent-default`, then `status-02`, `status-03`; second series hatched; value labels ≥ 12 px outside the bars; a one-sentence summary above each chart; an `aria-label` or table equivalent. |

## 5. States and messages

Every data view has loading, empty, error and success states. Errors say what failed and what to do («Не удалось загрузить данные. Повторите попытку»). Field errors name the field and the fix. Success after saving uses a toast; destructive actions confirm in a dialog that names the object.

## 6. Accessibility and responsiveness

- WCAG AA text contrast (4.5:1; 3:1 for large text and for input borders and focus).
- Visible focus on every interactive element (`--crm-focus-ring`).
- Keyboard: all actions reachable with Tab, Enter and Space; Esc closes dialogs, drawers and the phone menu.
- Layouts checked at 375, 768, 1024, 1280×600 and 1440 px: no page-wide horizontal scroll; the side menu reaches its last entry.
- `prefers-reduced-motion` respected.

## 7. Sign-in (Keycloak)

A UniCRM login theme in `deploy/keycloak/themes/unicrm/login/` (parent: Keycloak's built-in login theme): one stylesheet with the tokens above, Rostelecom Basis, the UniCRM wordmark and the organisation line. It covers sign-in, first-sign-in password change, password reset, error and sign-out confirmation, in Russian. It is mounted read-only in `compose.yaml`; `scripts/keycloak-set-login-theme.sh` sets `loginTheme` on the existing realm, and the realm file sets it for new installations. Rollback: set `loginTheme` back to the default and restart Keycloak.

## 8. Out of scope

- New features, including Excel/PDF export and column settings on Universities, and new list columns (listed in the audit doc for a later decision).
- Any `@atomaro/*` package.
- Live LMS or website integrations (permanent mocks).
- Backend changes, except the Keycloak theme mount and script.
- Dark mode (the tokens allow it later).

## 9. Acceptance for the whole redesign

All listed sections use one system; every existing task can be completed by each role without lost actions or data; frontend tests, type check, lint and build pass; the audit script reports no page-wide horizontal scroll, no text under 12 px, no phone control under 44 px and no text below AA; before/after screenshots and a release checklist are delivered. Publishing needs separate owner approval.
