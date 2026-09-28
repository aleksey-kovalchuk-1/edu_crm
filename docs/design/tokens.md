# Design tokens

All visual values live as CSS custom properties in the `:root` block at the top of `frontend/src/styles.css`.
Component rules use tokens only — no raw colours, font sizes or radii; `frontend/src/styles.test.ts` enforces this.

Source: the Rostelecom Gen2 (Atomaro) **Purple light** theme — CSS variables of `.Theme_root_rtk_purple_light`
in the Rostelecom React Storybook (Design Tokens stories), read on 28 Sep 2026. Names keep the `--atmr-` prefix
so they compare one to one with the Storybook; UniCRM additions use `--crm-`. No `@atomaro/*` package is used:
the values are reproduced in UniCRM's own CSS. Design system: `docs/superpowers/specs/2026-09-28-rostelecom-redesign-design.md`.

## Rules

- No text below 12 px; routine data at least 14 px; body text 16 px.
- Phone tap targets at least 44×44 px, with at least 8 px between neighbours.
- Status text uses the darker steps (`-700`, `-800`, `-600`), never `-default`.
- Colour never carries meaning alone: stages and chart series always have a text label.

## 2.1 Colour

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

## 2.2 Typography

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

## 2.3 Space, size, shape

- Spacing: `--atmr-spacing-1x` … `-12x` = 4, 8, 12, 16, 20, 24, 32, 40, 48 px (the same 4 px grid as today).
- Control heights: `--atmr-size-m` 36 px (desktop compact), `--atmr-size-l` 48 px (default fields and primary buttons). Every tappable control is at least 44×44 px below 768 px; small visuals (20 px checkbox) get a 44 px hit area.
- Radius: `--atmr-border-radius-m` 8 px (controls), `-l` 12 px (tables, dialogs, drawers), `-full` (chips, tags, counters).
- Border widths: dividers 1 px, inputs 2 px.
- Shadows: `--atmr-shadow-bottom-s` / `-m` only for layers above the page (dropdowns, popovers, drawers, dialogs, the phone menu). Page sections have no shadow.
- Motion: `--atmr-motion-duration-s` 200 ms with `--atmr-motion-easing-productive-standard`; 0 ms under `prefers-reduced-motion: reduce`.
- Breakpoints: `--atmr-breakpoint-s` 768, `-m` 1024, `-l` 1280 px.
- Layers: `--atmr-z-index-dropdown` 1000, `-sticky` 1100, `-overlay` 1300, `-modal` 1500, `-toast` 1600, `-popover` 1700, `-tooltip` 1800.

## UniCRM overrides (contrast)

| Token | Value | Why |
| --- | --- | --- |
| `--crm-input-border` | `var(--atmr-neutral-400)` | The theme's input border (`border-muted`) is 1.24:1; this is 4.06:1 |
| `--crm-focus-ring` | 2 px solid `--atmr-accent-default`, 2 px offset | The theme's focus colour is 1.13:1; this is 6.5:1 |
| `--crm-overlay` | `rgba(16, 24, 40, 0.5)` | Dialog backdrop |
| Status text | `-700` / `-800` / `-600` steps | The `-default` steps fail as text |


## Legacy names (aliases)

Today's names — `--color-*`, `--chart-*`, `--sidebar-*`, `--text-*`, `--weight-*`, `--radius-*`, `--shadow-*`,
`--focus-ring`, `--font-sans` — are aliases of the tokens above (see the `:root` block for the mapping).
Rules are moved to the `--atmr-*` names as each page is redesigned; the aliases are removed in Stage 5.
`--shadow-xs`, `--shadow-sm` and `--shadow-accent` are `none`: page sections have no shadow.
