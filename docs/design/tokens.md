# Design tokens

All visual values live as CSS custom properties in the `:root` block at the top of
`frontend/src/styles.css`. Component rules reference tokens only — no raw colours, font sizes or
radii. `frontend/src/styles.test.ts` enforces this.

## Colour

| Group | Tokens | Use |
|---|---|---|
| Neutrals | `--color-bg`, `--color-surface`, `--color-surface-subtle`, `--color-surface-muted` | Page background, panels, table headers / hover, tinted fills |
| Borders | `--color-border-subtle`, `--color-border`, `--color-border-strong` | Dividers, inputs and cards, hover / emphasis |
| Text | `--color-text`, `--color-text-secondary`, `--color-text-muted`, `--color-text-subtle`, `--color-text-inverse` | Headings and body, table cells, secondary text, captions and placeholders, text on the accent |
| Accent | `--color-accent`, `-hover`, `-strong`, `-soft`, `-border`, `--color-focus`, `--color-overlay` | Primary actions, links, selected states, focus ring, modal backdrop |
| Status | `--color-{success,warning,danger,info}` plus `-soft` / `-border` | Badges, alerts, deadlines |
| Charts | `--chart-{violet,violet-soft,blue,green,orange,grey}` | Data visualisation only, never text |
| Sidebar | `--sidebar-*` | The dark navigation column only |

Contrast (WCAG AA, 4.5:1 for normal text) is checked for every text token against the surfaces it
sits on. The lowest pair is `--color-text-subtle` on `--color-surface-muted` at 4.75:1. Each status
text colour is at least 5.5:1 on its own `-soft` background.

## Typography

Manrope (`--font-sans`). Base size is 14px (`--text-base`).

| Token | px | Typical use |
|---|---|---|
| `--text-2xs` | 11 | Table headers, badges, captions (the minimum) |
| `--text-xs` | 12 | Secondary labels |
| `--text-sm` | 13 | Table cells, form labels |
| `--text-base` | 14 | Body text |
| `--text-md` | 16 | Section headings (h2/h3), primary tabs |
| `--text-lg` … `--text-5xl` | 18–36 | Page headings, metrics |

Weights: `--weight-regular` 400, `-medium` 500, `-semibold` 600, `-bold` 700, `-heavy` 800.

## Spacing, radii, elevation

- Spacing is a 4px grid: `--space-0_5` (2px), `--space-1` (4px), `--space-1_5` (6px), then
  `--space-2` … `--space-12` (8–48px). Negative offsets use `calc(-1 * var(--space-n))`.
- Radii: `--radius-xs` 4px, `-sm` 6px, `-md` 8px, `-lg` 12px, `-pill`.
- Shadows: `--shadow-xs`, `-sm`, `-md`, `-accent`, `-overlay`, `-sidebar`, `--focus-ring`.

Layout sizes (sidebar width, column widths, icon boxes) stay literal: they are component
dimensions, not part of the scale.
