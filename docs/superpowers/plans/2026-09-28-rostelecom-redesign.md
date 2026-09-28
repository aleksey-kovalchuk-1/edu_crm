# UniCRM Rostelecom Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the whole UniCRM interface onto the Rostelecom Purple light design system in five reviewable stages, without changing any workflow, permission, calculation, export or authentication behaviour.

**Dry run:** Tasks 2–7 were applied as written to a throwaway checkout of `03c0e77` on 28 Sep 2026 (not committed): 404/404 frontend tests, `tsc`, ESLint and `vite build` pass. Task 1 (audit tool) and Task 8 (stack verification) were not dry-run.

**Architecture:** UniCRM keeps its own React components and one global stylesheet. Stage 1 adds the Rostelecom token layer (`--atmr-*`, values copied from the Storybook Purple light theme) plus UniCRM contrast overrides (`--crm-*`), turns today's token names into aliases of it, ships Rostelecom Basis, and rebuilds the shell (top bar, grouped scrolling side menu, phone drawer). Stages 2–5 restyle controls and pages rule by rule and remove the aliases at the end. No `@atomaro/*` packages.

**Tech Stack:** React 19, TypeScript, react-router 7, TanStack Query 5, Vitest + Testing Library (jsdom), ESLint, Vite 6; `playwright-core` (dev only) driving the installed Google Chrome for the layout audit; Keycloak 26.7.3 FreeMarker login theme (Stage 5).

**Spec:** `docs/superpowers/specs/2026-09-28-rostelecom-redesign-design.md` (token names and values, component rules, menu groups, acceptance).

## Global Constraints

- Start from the latest `origin/main` (last confirmed `03c0e77`; re-check with `git fetch && git rev-parse origin/main`). If `ai/fix-sidebar-scroll` has been merged, build on it; if not, Stage 1 still makes the side menu scroll (Task 7) and removes the flyout (Task 5).
- No `@atomaro/*` dependency. Token names keep the `--atmr-` prefix; UniCRM additions use `--crm-`.
- Theme: Rostelecom Purple light only. Accent `#7700ff`.
- Font: Rostelecom Basis 400/500/700 `woff2`, shipped from `frontend/src/assets/fonts/`. No Google Fonts.
- No text below 12 px; routine data at least 14 px; phone tap targets at least 44×44 px.
- Every colour, size, radius, shadow, duration comes from a `:root` token (`frontend/src/styles.test.ts` enforces this).
- Keep every menu entry's name, icon, role rule and order within its group; keep «Демонстрационный контур» and «Рабочий шаблон · Данные вымышлены» texts and their `VITE_DEMO_MODE` condition.
- LMS and website APIs are permanent mocks. No new features.
- Verification runs only against an isolated Compose project `edu-crm-verify` (port 18080, own volumes, throwaway Keycloak passwords), torn down afterwards. Never against production.
- No merge, deploy or launch-agent install without the owner's explicit approval. **Owner decision 28 Sep 2026:** Stages 1, 2, 3 and 3S (Settings) run consecutively without approval stops; each ends with a progress report. After 3S: screenshots, test results, remaining issues and a draft PR to `main` (push of the branch approved); no deployment until the owner reviews the combined result.
- `ui-ux-pro-max` (installed with approval into `.claude/skills`, untracked) is used for targeted UX checks; the Rostelecom rules take precedence. Findings applied: focusable error summary plus inline errors on failed save; contextual announcement of the unread count; ≥ 8 px between touch targets; sticky top bar must not hide the focused element (`scroll-padding-top`); no flashing loaders for near-instant work; empty states with a next action.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A touch tap on «Настройки»** fires `mouseenter` then `click`. Expected: the group opens and stays open. (Task 5 test `a tap (hover then click) opens the group and leaves it open`.)
2. **Role-dependent menu groups.** A group whose entries are all hidden for the role must not render an empty heading; a manager still sees «Данные клиентов» with three entries. (Task 4 tests.)
3. **Short desktop screens** (1280×600). Expected: the side menu's last entry and «Выйти» are reachable. (Task 7 CSS test + Task 8 audit.)
4. **Font-size bump** (11→12, 13→14 px) on dense tables and boards at 1024 px. Expected: no page-wide horizontal scroll. (Task 8 audit `pageOverflowX`.)
5. **Status and muted text** on tinted backgrounds after the colour switch. Expected: AA contrast. (Task 2 alias test + Task 8 audit `lowContrast`.)

---

## File structure (Stage 1)

| File | Responsibility |
| --- | --- |
| `frontend/scripts/ui-audit.mjs` (new) | Signs in to the isolated stack, screenshots pages at given sizes, measures overflow, text sizes, contrast, tap targets, focus and side-menu reach |
| `frontend/package.json` | Adds `playwright-core` (dev) and the `audit:ui` script |
| `frontend/src/styles.css` | Token layer, font faces, shell rules |
| `frontend/src/styles.test.ts` | Token, font and shell guards |
| `frontend/src/assets/fonts/RostelecomBasis-{Regular,Medium,Bold}.woff2` (new) | Shipped font |
| `frontend/src/app/navigation.ts` | Adds `navGroups()` |
| `frontend/src/app/navigation.test.ts` | Group tests |
| `frontend/src/app/SettingsMenu.tsx` | Becomes an in-menu disclosure group |
| `frontend/src/app/SettingsMenu.test.tsx` | Rewritten for the disclosure |
| `frontend/src/app/Layout.tsx` | Top bar with profile and «Выйти»; grouped menu; drawer behaviour |
| `frontend/src/app/Layout.test.tsx`, `App.test.tsx` | Shell tests; menu-item role changes |
| `docs/design/tokens.md` | Rewritten for the new token layer |

---

## Stage 1 — Tokens, font and shell

### Task 1: Layout audit tool

**Files:**
- Create: `frontend/scripts/ui-audit.mjs`
- Modify: `frontend/package.json` (devDependencies, scripts), `frontend/eslint.config.js` (Node scripts block)

**Interfaces:**
- Produces: `npm run audit:ui -- --role <super|admin|manager> --pages <comma list> --sizes <WxH,...> --out <dir>`; env `AUDIT_BASE` (default `http://localhost:18080`), `AUDIT_ACCOUNTS` (path to a `LOGIN_PASSWORD=...` file). Writes `<out>/metrics-<role>.json` and `<out>/shots/*.png`. Exit code 1 if any page has `pageOverflowX`, text under 12 px, or (below 768 px) a control under 44 px.

- [ ] **Step 1: Add the dependency, pinned**

Run: `cd frontend && npm view playwright-core version` and install exactly that stable version: `npm install --save-dev --save-exact playwright-core@<printed version>`.
Expected: `package.json` gains `"playwright-core": "<exact version>"` under devDependencies; `package-lock.json` updated. The tool uses the installed Google Chrome (`channel: "chrome"`), so no browser download.

- [ ] **Step 2: Add the script entry**

In `frontend/package.json` `scripts`, add: `"audit:ui": "node scripts/ui-audit.mjs"`.

- [ ] **Step 3: Let ESLint check Node scripts**

`frontend/eslint.config.js` only covers `**/*.{ts,tsx,js}` with browser globals. Add a second entry to the `defineConfig([...])` array:

```js
  {
    files: ["scripts/**/*.mjs"],
    extends: [js.configs.recommended],
    languageOptions: { ecmaVersion: 2024, sourceType: "module", globals: globals.node },
  },
```

- [ ] **Step 4: Write the tool**

```js
// frontend/scripts/ui-audit.mjs
// Layout audit for the isolated verification stack (never production). Passwords are read from a
// file and never printed.
import { chromium } from "playwright-core";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";

const { values: args } = parseArgs({
  options: {
    role: { type: "string" },
    pages: { type: "string" },
    sizes: { type: "string", default: "1440x900,1280x600,1024x768,768x1024,375x812" },
    out: { type: "string" },
  },
});
const LOGINS = { super: "irina_super_admin", admin: "admin_1", manager: "manager_1" };
const base = process.env.AUDIT_BASE ?? "http://localhost:18080";
const login = LOGINS[args.role];
if (!login || !args.pages || !args.out || !process.env.AUDIT_ACCOUNTS) {
  console.error("usage: AUDIT_ACCOUNTS=file npm run audit:ui -- --role super|admin|manager --pages /,/tasks --out dir");
  process.exit(2);
}
const accounts = Object.fromEntries(
  readFileSync(process.env.AUDIT_ACCOUNTS, "utf8").trim().split("\n").map((l) => l.split(/=(.*)/s).slice(0, 2)),
);
mkdirSync(`${args.out}/shots`, { recursive: true });

function measure() {
  const vw = innerWidth;
  const lum = (c) => {
    const m = c.match(/[\d.]+/g);
    if (!m) return null;
    const [r, g, b, a = 1] = m.map(Number);
    const l = [r, g, b].map((v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return { l: 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2], a };
  };
  const bgOf = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const L = lum(getComputedStyle(e).backgroundColor);
      if (L && L.a > 0.9) return L.l;
    }
    return 1;
  };
  const texts = [...document.querySelectorAll("body *")].filter(
    (e) => e.offsetParent !== null && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()),
  );
  const small = [];
  const lowContrast = [];
  for (const e of texts) {
    const cs = getComputedStyle(e);
    const size = parseFloat(cs.fontSize);
    if (size < 12) small.push(`${size}px «${e.textContent.trim().slice(0, 30)}»`);
    const fg = lum(cs.color);
    if (!fg || fg.a < 0.9) continue;
    const bg = bgOf(e);
    const ratio = (Math.max(fg.l, bg) + 0.05) / (Math.min(fg.l, bg) + 0.05);
    const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
    if (ratio < (large ? 3 : 4.5)) lowContrast.push(`${ratio.toFixed(2)} ${size}px «${e.textContent.trim().slice(0, 30)}»`);
  }
  const controls = [...document.querySelectorAll("a[href], button, input, select, textarea, [role=button]")].filter(
    (e) => e.offsetParent !== null && !e.closest("label"),
  );
  const tiny = controls
    .map((e) => [e, e.getBoundingClientRect()])
    .filter(([, r]) => r.width > 0 && (r.width < 44 || r.height < 44))
    .map(([e, r]) => `${e.tagName.toLowerCase()} ${Math.round(r.width)}×${Math.round(r.height)} «${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 24)}»`);
  const menu = document.querySelector(".sidebar");
  let menuReach = null;
  if (menu && getComputedStyle(menu).visibility !== "hidden" && menu.getBoundingClientRect().right > 0) {
    menu.scrollTop = menu.scrollHeight;
    const last = [...menu.querySelectorAll("a, button")].at(-1)?.getBoundingClientRect();
    menuReach = !!last && last.bottom <= innerHeight + 1;
  }
  return {
    pageOverflowX: document.documentElement.scrollWidth > vw,
    small: [...new Set(small)].slice(0, 10),
    lowContrast: [...new Set(lowContrast)].slice(0, 10),
    tiny: vw < 768 ? tiny.slice(0, 10) : [],
    menuReach,
    h1: document.querySelector("h1")?.textContent ?? null,
  };
}

const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ locale: "ru-RU" })).newPage();
await page.goto(`${base}/`);
await page.waitForSelector("#username", { timeout: 30000 });
await page.fill("#username", login);
await page.fill("#password", accounts[`${login.toUpperCase()}_PASSWORD`]);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/auth"), { timeout: 30000 }), page.click("#kc-login")]);

const report = {};
let failed = false;
for (const size of args.sizes.split(",")) {
  const [width, height] = size.split("x").map(Number);
  await page.setViewportSize({ width, height });
  for (const path of args.pages.split(",")) {
    const name = `${args.role}-${path === "/" ? "overview" : path.slice(1).replaceAll("/", "_")}-${size}`;
    await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${args.out}/shots/${name}.png`, fullPage: true });
    const m = await page.evaluate(measure);
    report[name] = m;
    if (m.pageOverflowX || m.small.length || m.tiny.length || m.menuReach === false) failed = true;
  }
}
writeFileSync(`${args.out}/metrics-${args.role}.json`, JSON.stringify(report, null, 1));
await browser.close();
console.log(`${Object.keys(report).length} captures; ${failed ? "FAILURES — see metrics" : "all checks passed"}`);
process.exit(failed ? 1 : 0);
```

- [ ] **Step 5: Check it runs and lints**

Run: `cd frontend && npx eslint scripts/ui-audit.mjs && node scripts/ui-audit.mjs; echo "exit $?"`
Expected: lint clean; usage message and `exit 2` (no arguments).

- [ ] **Step 6: Record the "before" baseline**

Bring up the isolated stack from the untouched base commit (commands in Task 8, Step 3), then run for each role:
`AUDIT_ACCOUNTS=../deploy/local/verify-accounts.env npm run audit:ui -- --role super --pages /,/universities,/universities/1,/contracts,/interactions,/interactions/board,/tasks,/analytics,/reports,/settings/profile --out ../../ui-audit/before`
Expected: runs; exit 1 (today's UI has 11 px text and small targets). Keep the output outside the repository.

- [ ] **Step 7: Commit**

```bash
git add frontend/scripts/ui-audit.mjs frontend/eslint.config.js frontend/package.json frontend/package-lock.json
git commit -m "Add a layout audit tool for the isolated verification stack"
```

### Task 2: Rostelecom token layer with legacy aliases

**Files:**
- Modify: `frontend/src/styles.css` (the whole `:root { … }` block)
- Test: `frontend/src/styles.test.ts`

**Interfaces:**
- Produces: `--atmr-*` and `--crm-*` custom properties (spec §2) used by Tasks 3, 7 and later stages; all existing `--color-*`, `--chart-*`, `--sidebar-*`, `--text-*`, `--weight-*`, `--radius-*`, `--shadow-*`, `--focus-ring`, `--font-sans` names keep working as aliases.

- [ ] **Step 1: Write the failing tests**

Add inside `describe("styles.css design tokens", …)` in `frontend/src/styles.test.ts`, and change the existing 11 px test to 12 px:

```ts
  it("has no text token smaller than 12px", () => {
    const px = [...tokens.matchAll(/--text-[\w]+:\s*(\d+)px/g)].map((m) => Number(m[1]));
    expect(px.length).toBeGreaterThan(0);
    expect(Math.min(...px)).toBeGreaterThanOrEqual(12);
  });

  it("uses the Rostelecom Purple light accent", () => {
    expect(tokens).toMatch(/--atmr-accent-default:\s*#7700ff;/);
    expect(tokens).toMatch(/--atmr-fg-default:\s*#101828;/);
  });

  it("points every legacy colour token at a Rostelecom or UniCRM token", () => {
    const legacy = [...tokens.matchAll(/--(?:color|chart|sidebar)-[\w-]+:\s*([^;]+);/g)].map((m) => m[1].trim());
    expect(legacy.length).toBeGreaterThan(30);
    expect(legacy.filter((v) => !/^var\(--(?:atmr|crm)-[\w-]+\)$/.test(v))).toEqual([]);
  });

  it("draws focus as a 2px accent ring with a 2px gap (6.5:1 on white)", () => {
    expect(tokens).toMatch(/--crm-focus-ring:\s*0 0 0 2px var\(--atmr-bg-surface1\), 0 0 0 4px var\(--atmr-accent-default\);/);
    expect(tokens).toMatch(/--focus-ring:\s*var\(--crm-focus-ring\);/);
  });
```

Delete the old `it("has no text token smaller than 11px", …)` block.

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd frontend && npx vitest run src/styles.test.ts`
Expected: FAIL — "uses the Rostelecom Purple light accent", "points every legacy colour token…", "draws focus…", and "no text token smaller than 12px" (11 px exists).

- [ ] **Step 3: Replace the `:root` block**

Replace everything from `:root {` to its closing `}` (the block that starts `/* ——— Design tokens`) with:

```css
:root {
  /* ——— Rostelecom Purple light (Atomaro Gen2), values from .Theme_root_rtk_purple_light in the Storybook.
         Names match the Storybook one to one. See docs/design/tokens.md. ——— */
  --atmr-bg-page: #fff;
  --atmr-bg-surface1: #fff;
  --atmr-bg-surface2: #f9f9fa;
  --atmr-bg-surface3: #f4f4f5;
  --atmr-bg-surface4: #e8e8ee;
  --atmr-fg-default: #101828;
  --atmr-fg-soft: rgba(16, 24, 40, 0.75);
  --atmr-fg-muted: rgba(16, 24, 40, 0.55);
  --atmr-border-muted: rgba(88, 93, 105, 0.15);
  --atmr-border-soft: rgba(88, 93, 105, 0.25);
  --atmr-border-default: rgba(88, 93, 105, 0.5);
  --atmr-neutral-400: #797e8b;
  --atmr-neutral-500: #585d69;
  --atmr-neutral-container-default: rgba(88, 93, 105, 0.1);
  --atmr-neutral-container-hover: rgba(88, 93, 105, 0.2);
  --atmr-accent-default: #7700ff;
  --atmr-accent-hover: #6500d9;
  --atmr-accent-active: #5300b3;
  --atmr-accent-muted: #bb80ff;
  --atmr-accent-on-accent: #fff;
  --atmr-accent-container-default: rgba(119, 0, 255, 0.1);
  --atmr-accent-container-soft: rgba(119, 0, 255, 0.05);
  --atmr-accent-container-hover: rgba(119, 0, 255, 0.2);
  --atmr-success-default: #00ac43;
  --atmr-success-700: #00782f;
  --atmr-success-muted: #80d6a1;
  --atmr-success-container-default: rgba(0, 172, 67, 0.1);
  --atmr-warning-default: #fda610;
  --atmr-warning-800: #98640a;
  --atmr-warning-muted: #fed388;
  --atmr-warning-container-default: rgba(253, 166, 16, 0.1);
  --atmr-error-default: #ff2626;
  --atmr-error-700: #b31b1b;
  --atmr-error-muted: #ff9393;
  --atmr-error-container-default: rgba(255, 38, 38, 0.1);
  --atmr-info-default: #1f69ff;
  --atmr-info-600: #1a59d9;
  --atmr-info-muted: #8fb4ff;
  --atmr-info-container-default: rgba(31, 105, 255, 0.1);
  --atmr-status-01-default: #ff4f12;
  --atmr-status-02-default: #4055e8;
  --atmr-status-03-default: #038fde;
  --atmr-status-04-default: #1898a9;
  --atmr-status-05-default: #ca20d9;
  --atmr-status-06-default: #d9206f;

  --atmr-font-family-base: "Rostelecom Basis", Arial, sans-serif;
  --atmr-font-heading-h1: 700 28px/32px var(--atmr-font-family-base);
  --atmr-font-heading-h2: 700 22px/24px var(--atmr-font-family-base);
  --atmr-font-heading-h3: 700 18px/20px var(--atmr-font-family-base);
  --atmr-font-body-m: 400 16px/24px var(--atmr-font-family-base);
  --atmr-font-body-m-strong: 500 16px/24px var(--atmr-font-family-base);
  --atmr-font-body-s: 400 14px/20px var(--atmr-font-family-base);
  --atmr-font-body-s-strong: 500 14px/20px var(--atmr-font-family-base);
  --atmr-font-description-l: 400 12px/16px var(--atmr-font-family-base);
  --atmr-font-description-l-strong: 500 12px/16px var(--atmr-font-family-base);

  --atmr-spacing-1x: 4px;
  --atmr-spacing-2x: 8px;
  --atmr-spacing-3x: 12px;
  --atmr-spacing-4x: 16px;
  --atmr-spacing-5x: 20px;
  --atmr-spacing-6x: 24px;
  --atmr-spacing-8x: 32px;
  --atmr-spacing-10x: 40px;
  --atmr-spacing-12x: 48px;
  --atmr-size-m: 36px;
  --atmr-size-l: 48px;
  --atmr-border-radius-xs: 4px;
  --atmr-border-radius-s: 6px;
  --atmr-border-radius-m: 8px;
  --atmr-border-radius-l: 12px;
  --atmr-border-radius-full: 9999px;
  --atmr-shadow-bottom-s: 0 0 8px 0 rgba(88, 93, 105, 0.1), 0 2px 4px 0 rgba(88, 93, 105, 0.05);
  --atmr-shadow-bottom-m: 0 0 16px 0 rgba(88, 93, 105, 0.1), 0 4px 8px 0 rgba(88, 93, 105, 0.05);
  --atmr-shadow-bottom-xl: 0 0 32px 0 rgba(88, 93, 105, 0.1), 0 32px 32px 0 rgba(88, 93, 105, 0.05);
  --atmr-motion-duration-s: 200ms;
  --atmr-motion-easing-productive-standard: cubic-bezier(0.4, 0, 0.6, 1);
  --atmr-z-index-sticky: 1100;
  --atmr-z-index-overlay: 1300;

  /* ——— UniCRM overrides for contrast (spec §2.5) ——— */
  --crm-input-border: var(--atmr-neutral-400);
  --crm-focus-ring: 0 0 0 2px var(--atmr-bg-surface1), 0 0 0 4px var(--atmr-accent-default);
  --crm-overlay: rgba(16, 24, 40, 0.5);
  --crm-hatch-light: #6ec0ee;

  /* ——— Legacy names, kept as aliases until Stage 5 removes them ——— */
  --color-bg: var(--atmr-bg-page);
  --color-surface: var(--atmr-bg-surface1);
  --color-surface-subtle: var(--atmr-bg-surface2);
  --color-surface-muted: var(--atmr-bg-surface3);
  --color-border-subtle: var(--atmr-border-muted);
  --color-border: var(--atmr-border-soft);
  --color-border-strong: var(--atmr-border-default);
  --color-text: var(--atmr-fg-default);
  --color-text-secondary: var(--atmr-fg-soft);
  --color-text-muted: var(--atmr-fg-soft);
  --color-text-subtle: var(--atmr-fg-soft);
  --color-text-inverse: var(--atmr-accent-on-accent);
  --color-accent: var(--atmr-accent-default);
  --color-accent-hover: var(--atmr-accent-hover);
  --color-accent-strong: var(--atmr-accent-active);
  --color-accent-soft: var(--atmr-accent-container-default);
  --color-accent-border: var(--atmr-accent-muted);
  --color-focus: var(--atmr-accent-default);
  --color-overlay: var(--crm-overlay);
  --color-success: var(--atmr-success-700);
  --color-success-soft: var(--atmr-success-container-default);
  --color-success-border: var(--atmr-success-muted);
  --color-warning: var(--atmr-warning-800);
  --color-warning-soft: var(--atmr-warning-container-default);
  --color-warning-border: var(--atmr-warning-muted);
  --color-danger: var(--atmr-error-700);
  --color-danger-soft: var(--atmr-error-container-default);
  --color-danger-border: var(--atmr-error-muted);
  --color-info: var(--atmr-info-600);
  --color-info-soft: var(--atmr-info-container-default);
  --color-info-border: var(--atmr-info-muted);
  --chart-violet: var(--atmr-accent-default);
  --chart-violet-soft: var(--atmr-accent-muted);
  --chart-blue: var(--atmr-status-02-default);
  --chart-green: var(--atmr-status-04-default);
  --chart-orange: var(--atmr-status-01-default);
  --chart-grey: var(--atmr-neutral-400);
  --sidebar-bg: var(--atmr-bg-surface2);
  --sidebar-text: var(--atmr-fg-default);
  --sidebar-text-strong: var(--atmr-fg-default);
  --sidebar-text-muted: var(--atmr-fg-soft);
  --sidebar-accent: var(--atmr-accent-active);
  --sidebar-hover: var(--atmr-neutral-container-default);
  --sidebar-border: var(--atmr-border-soft);
  --sidebar-online: var(--atmr-success-default);

  --font-sans: var(--atmr-font-family-base);
  --text-2xs: 12px;
  --text-xs: 12px;
  --text-sm: 14px;
  --text-base: 14px;
  --text-md: 16px;
  --text-lg: 18px;
  --text-xl: 20px;
  --text-2xl: 24px;
  --text-3xl: 28px;
  --text-4xl: 32px;
  --text-5xl: 36px;
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-semibold: 500;
  --weight-bold: 700;
  --weight-heavy: 700;

  --space-0_5: 2px;
  --space-1: 4px;
  --space-1_5: 6px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;

  --radius-xs: var(--atmr-border-radius-xs);
  --radius-sm: var(--atmr-border-radius-s);
  --radius-md: var(--atmr-border-radius-m);
  --radius-lg: var(--atmr-border-radius-l);
  --radius-pill: var(--atmr-border-radius-full);

  --shadow-xs: none;
  --shadow-sm: none;
  --shadow-md: var(--atmr-shadow-bottom-m);
  --shadow-accent: none;
  --shadow-overlay: var(--atmr-shadow-bottom-xl);
  --shadow-sidebar: var(--atmr-shadow-bottom-m);
  --focus-ring: var(--crm-focus-ring);
}
@media (prefers-reduced-motion: reduce) {
  :root {
    --atmr-motion-duration-s: 0ms;
  }
}
```

(`--shadow-xs`, `-sm` and `-accent` become `none`: page sections lose their shadows; raised layers keep `-md` and `-overlay`. Rostelecom Basis has no 600 weight, so `--weight-semibold` maps to 500.)

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/styles.test.ts`
Expected: PASS, including the pre-existing "keeps colours in tokens only" and "uses the type scale" tests.

Note for the executor: the `:root` extraction in `styles.test.ts` ends at the first `}` after `:root {`; the block above contains no nested braces, and the reduced-motion `:root` sits outside it inside `@media`, where the colour test sees no raw colours.

- [ ] **Step 5: Run the whole frontend suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npx eslint .`
Expected: all pass (no component test asserts colours).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles.css frontend/src/styles.test.ts
git commit -m "Add the Rostelecom Purple light token layer; alias the old tokens to it"
```

### Task 3: Ship Rostelecom Basis

**Files:**
- Create: `frontend/src/assets/fonts/RostelecomBasis-Regular.woff2`, `-Medium.woff2`, `-Bold.woff2` (the three files downloaded with the owner's approval on 28 Sep 2026 from the Storybook; 48,884 / 48,524 / 48,024 bytes; `file` reports "Web Open Font Format (Version 2)")
- Modify: `frontend/src/styles.css` (first line: the Google Fonts `@import`)
- Test: `frontend/src/styles.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
  it("loads Rostelecom Basis from the app's own files, not Google Fonts", () => {
    expect(css).not.toMatch(/fonts\.googleapis\.com/);
    for (const [weight, file] of [[400, "Regular"], [500, "Medium"], [700, "Bold"]] as const) {
      expect(css).toMatch(
        new RegExp(
          `@font-face\\s*\\{\\s*font-family:\\s*"Rostelecom Basis";\\s*src:\\s*url\\("\\./assets/fonts/RostelecomBasis-${file}\\.woff2"\\) format\\("woff2"\\);\\s*font-weight:\\s*${weight};`,
        ),
      );
    }
  });
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx vitest run src/styles.test.ts -t "Rostelecom Basis"`
Expected: FAIL (the Manrope import is present, no `@font-face`).

- [ ] **Step 3: Add the files and the font faces**

Copy the three `woff2` files into `frontend/src/assets/fonts/`. Replace the first line of `styles.css` (`@import url("https://fonts.googleapis.com/css2?family=Manrope…");`) with:

```css
@font-face {
  font-family: "Rostelecom Basis";
  src: url("./assets/fonts/RostelecomBasis-Regular.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Rostelecom Basis";
  src: url("./assets/fonts/RostelecomBasis-Medium.woff2") format("woff2");
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Rostelecom Basis";
  src: url("./assets/fonts/RostelecomBasis-Bold.woff2") format("woff2");
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}
```

- [ ] **Step 4: Run tests and build**

Run: `cd frontend && npx vitest run src/styles.test.ts && npx vite build 2>&1 | grep -c RostelecomBasis`
Expected: PASS; the build output lists three `RostelecomBasis-*.woff2` assets (count 3).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/assets/fonts frontend/src/styles.css frontend/src/styles.test.ts
git commit -m "Ship Rostelecom Basis with the app and drop the Google Fonts import"
```

### Task 4: Menu groups

**Files:**
- Modify: `frontend/src/app/navigation.ts` (append after `visiblePages`)
- Test: `frontend/src/app/navigation.test.ts`

**Interfaces:**
- Consumes: `pages`, `paths`, `visiblePages(roles)`, `PageMeta` (existing).
- Produces: `type NavGroupId = "work" | "analysis" | "customers" | "admin"`; `interface NavGroup { id: NavGroupId; label: string; pages: PageMeta[]; hasSettings: boolean }`; `navGroups(roles: string[]): NavGroup[]`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/navigation.test.ts` (and extend its import to `import { navGroups, pages, paths, settingsPages, visiblePages } from "./navigation";`):

```ts
describe("menu groups", () => {
  const allRoles = [ROLES.user, ROLES.supervisor, ROLES.admin, ROLES.superadmin];

  it("puts every visible page in exactly one group", () => {
    const grouped = navGroups(allRoles).flatMap((g) => g.pages.map((p) => p.path));
    expect([...grouped].sort()).toEqual(visiblePages(allRoles).map((p) => p.path).sort());
    expect(new Set(grouped).size).toBe(grouped.length);
  });

  it("keeps the current order of pages inside each group", () => {
    const order = pages.map((p) => p.path);
    for (const g of navGroups(allRoles)) {
      const idx = g.pages.map((p) => order.indexOf(p.path));
      expect(idx).toEqual([...idx].sort((a, b) => a - b));
    }
  });

  it("labels the groups Работа, Анализ, Данные клиентов, Администрирование, with Настройки in the last", () => {
    const groups = navGroups(allRoles);
    expect(groups.map((g) => g.label)).toEqual(["Работа", "Анализ", "Данные клиентов", "Администрирование"]);
    expect(groups.map((g) => g.hasSettings)).toEqual([false, false, false, true]);
  });

  it("shows a manager the pages their role allows, grouped", () => {
    const names = Object.fromEntries(navGroups([ROLES.user]).map((g) => [g.label, g.pages.map((p) => p.name)]));
    expect(names).toEqual({
      "Работа": ["Обзор", "Учебные заведения", "Договоры", "Взаимодействия", "Задачи"],
      "Анализ": ["Аналитика", "Отчёты"],
      "Данные клиентов": ["Компании", "Слушатели", "Заявки на курсы"],
      "Администрирование": ["Справочники"],
    });
  });

  it("drops a group whose pages are all hidden, but keeps Администрирование for Настройки", () => {
    const groups = navGroups(["no-such-role"]);
    expect(groups.find((g) => g.id === "admin")?.hasSettings).toBe(true);
    expect(groups.every((g) => g.pages.length > 0 || g.hasSettings)).toBe(true);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/app/navigation.test.ts`
Expected: FAIL — `navGroups` is not exported.

- [ ] **Step 3: Implement**

Append to `frontend/src/app/navigation.ts` after `visiblePages`:

```ts
export type NavGroupId = "work" | "analysis" | "customers" | "admin";

export interface NavGroup {
  id: NavGroupId;
  label: string;
  pages: PageMeta[];
  /** The «Настройки» disclosure sits at the end of this group. */
  hasSettings: boolean;
}

/** Menu groups (spec §3.2). Pages keep their order from `pages`; settings pages live in SettingsMenu. */
const NAV_GROUPS: { id: NavGroupId; label: string; paths: string[] }[] = [
  { id: "work", label: "Работа", paths: [paths.overview, paths.universities, paths.contracts, paths.interactions, paths.tasks] },
  { id: "analysis", label: "Анализ", paths: [paths.analytics, paths.reports] },
  {
    id: "customers",
    label: "Данные клиентов",
    paths: [paths.vendors, paths.learners, paths.applications, paths.customerImports, paths.fraudAlerts],
  },
  { id: "admin", label: "Администрирование", paths: [paths.catalogs, paths.imports, paths.workflows] },
];

/** The side menu for a user's roles: groups with no visible page are dropped, except the one holding «Настройки». */
export function navGroups(roles: string[]): NavGroup[] {
  const visible = visiblePages(roles);
  return NAV_GROUPS.map((g) => ({
    id: g.id,
    label: g.label,
    pages: visible.filter((p) => g.paths.includes(p.path)),
    hasSettings: g.id === "admin",
  })).filter((g) => g.pages.length > 0 || g.hasSettings);
}
```

(`visible.filter(...)` keeps `pages` order, which the order test pins.)

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/app/navigation.test.ts`
Expected: PASS (all old and new tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/navigation.ts frontend/src/app/navigation.test.ts
git commit -m "Group the side menu into Работа, Анализ, Данные клиентов, Администрирование"
```

### Task 5: «Настройки» as an in-menu disclosure

**Files:**
- Modify: `frontend/src/app/SettingsMenu.tsx` (full rewrite)
- Test: `frontend/src/app/SettingsMenu.test.tsx` (full rewrite), `frontend/src/app/App.test.tsx` (menu-item queries)
- Modify: `frontend/src/styles.css` (remove `.settings-menu-*` rules and `@keyframes settings-menu-in`; add `.settings-group*`, `.nav-subitem` in Task 7)

**Interfaces:**
- Consumes: `PageMeta` (existing); the same props as today: `pages`, `currentPath`, `userRoles`, `onNavigate?`.
- Produces: `<SettingsMenu …/>` rendering a `button.nav-item` with `aria-expanded`/`aria-controls` and a `ul.settings-group-list` of `NavLink.nav-subitem` links. No `role="menu"`/`menuitem` any more.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `frontend/src/app/SettingsMenu.test.tsx` with:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { UserRound } from "lucide-react";
import { SettingsMenu } from "./SettingsMenu";
import type { PageMeta } from "./navigation";

const PAGES: PageMeta[] = [
  { path: "/settings/a", name: "Пункт А", icon: UserRound, heading: "А", subtitle: "", create: null, hidden: true },
  { path: "/settings/b", name: "Пункт Б", icon: UserRound, heading: "Б", subtitle: "", create: null, hidden: true },
  { path: "/settings/c", name: "Только для суперадмина", icon: UserRound, heading: "В", subtitle: "", create: null, hidden: true, roles: ["crm-superadmin"] },
];

function renderMenu(path = "/", props: Partial<React.ComponentProps<typeof SettingsMenu>> = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SettingsMenu pages={PAGES} currentPath={path} userRoles={["crm-user"]} {...props} />
    </MemoryRouter>,
  );
}
const trigger = () => screen.getByRole("button", { name: /Настройки/ });

describe("SettingsMenu", () => {
  it("is collapsed outside settings pages", () => {
    renderMenu("/");
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("link", { name: "Пункт А" })).toBeNull();
  });

  it("opens on click and stays open without hover", () => {
    renderMenu("/");
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    fireEvent.mouseLeave(trigger());
    expect(screen.getByRole("link", { name: "Пункт А" })).toBeTruthy();
  });

  it("a tap (hover then click) opens the group and leaves it open", () => {
    renderMenu("/");
    fireEvent.mouseEnter(trigger());
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("link", { name: "Пункт Б" })).toBeTruthy();
  });

  it("closes on a second click", () => {
    renderMenu("/");
    fireEvent.click(trigger());
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
  });

  it("is open on a settings page and marks the current item", () => {
    renderMenu("/settings/b");
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("link", { name: "Пункт Б" }).getAttribute("aria-current")).toBe("page");
    expect(trigger().className).toContain("active");
  });

  it("hides items the role may not see", () => {
    renderMenu("/settings/a");
    expect(screen.queryByRole("link", { name: "Только для суперадмина" })).toBeNull();
  });

  it("shows superadmin-only items to a superadmin", () => {
    renderMenu("/settings/a", { userRoles: ["crm-superadmin"] });
    expect(screen.getByRole("link", { name: "Только для суперадмина" })).toBeTruthy();
  });

  it("calls onNavigate when an item is chosen", () => {
    const onNavigate = vi.fn();
    renderMenu("/", { onNavigate });
    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole("link", { name: "Пункт А" }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it("links the button to the list it controls", () => {
    renderMenu("/settings/a");
    const list = document.getElementById(trigger().getAttribute("aria-controls")!);
    expect(list?.tagName).toBe("UL");
  });
});
```

In `frontend/src/app/App.test.tsx`, in `describe("Настройки menu", …)`:
- replace every `getByRole("menuitem", …)` / `queryByRole("menuitem", …)` with `getByRole("link", …)` / `queryByRole("link", …)` (same names);
- replace the adjacency assertion in the first test with:

```tsx
    const admin = within(nav).getByRole("group", { name: "Администрирование" });
    const links = within(admin).getAllByRole("link");
    expect(links.at(-1)?.textContent).toMatch(/Процессы/);
    const settingsButton = within(admin).getByRole("button", { name: /Настройки/ });
    expect(links.at(-1)!.compareDocumentPosition(settingsButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
```

(The `group` role and its name come from Task 6; these App tests go green at the end of Task 6.)

- [ ] **Step 2: Run the component tests to see them fail**

Run: `cd frontend && npx vitest run src/app/SettingsMenu.test.tsx`
Expected: FAIL — `aria-expanded` stays false after a tap; links are `menuitem`s; no `aria-current`.

- [ ] **Step 3: Rewrite the component**

Replace `frontend/src/app/SettingsMenu.tsx` with:

```tsx
import { useId, useState } from "react";
import { NavLink } from "react-router";
import { ChevronDown, Settings } from "lucide-react";
import type { PageMeta } from "./navigation";

/**
 * «Настройки» as a group inside the side menu (spec §3.2): a disclosure button and a list of
 * links. It opens by click, tap or keyboard only — no hover — so a touch tap (which fires hover
 * and then click) opens it instead of opening and closing it at once. It is open on settings pages.
 */
export function SettingsMenu({
  pages,
  currentPath,
  userRoles,
  onNavigate,
}: {
  pages: PageMeta[];
  currentPath: string;
  userRoles: string[];
  /** Called when an item is chosen: lets the layout close the phone menu and reset page state. */
  onNavigate?: () => void;
}) {
  const listId = useId();
  // Same rule visiblePages() uses: no roles listed means everyone sees it.
  const visible = pages.filter((p) => !p.roles || p.roles.some((r) => userRoles.includes(r)));
  const inSettings = visible.some((p) => currentPath === p.path || currentPath.startsWith(`${p.path}/`));
  // null = the user has not toggled it yet, so it follows the current page.
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? inSettings;

  return (
    <div className="settings-group">
      <button
        type="button"
        className={inSettings ? "nav-item active" : "nav-item"}
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setToggled(!open)}
      >
        <Settings size={20} aria-hidden="true" />
        Настройки
        <ChevronDown size={16} className="settings-group-chevron" aria-hidden="true" />
      </button>
      <ul id={listId} className="settings-group-list" hidden={!open}>
        {visible.map((p) => (
          <li key={p.path}>
            <NavLink
              to={p.path}
              className={({ isActive }) => (isActive ? "nav-subitem active" : "nav-subitem")}
              onClick={onNavigate}
            >
              <p.icon size={18} aria-hidden="true" />
              {p.name}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Remove the flyout styles**

In `frontend/src/styles.css`, delete the rule blocks whose selectors start with `.settings-menu-` (root, chevron, panel, panel-inner, item, item:hover/focus-visible), `@keyframes settings-menu-in`, and the `.settings-menu-panel` override inside `@media (max-width: 800px)`. If `ai/fix-sidebar-scroll` was merged, also delete its test `positions the desktop settings flyout as fixed…` from `styles.test.ts`.

- [ ] **Step 5: Run the component tests**

Run: `cd frontend && npx vitest run src/app/SettingsMenu.test.tsx`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit** (App tests are completed in Task 6)

```bash
git add frontend/src/app/SettingsMenu.tsx frontend/src/app/SettingsMenu.test.tsx frontend/src/app/App.test.tsx frontend/src/styles.css frontend/src/styles.test.ts
git commit -m "Turn Настройки into an in-menu group that opens by click or tap"
```

### Task 6: Shell markup — top bar, grouped menu, phone drawer

**Files:**
- Modify: `frontend/src/app/Layout.tsx`
- Test: `frontend/src/app/Layout.test.tsx`, `frontend/src/app/App.test.tsx` («topbar account avatar»), `frontend/src/app/auth.test.tsx` (avatar count)

**Interfaces:**
- Consumes: `navGroups(roles)` (Task 4), `SettingsMenu` (Task 5), existing `useBrand`, `useSession`, `useSignOut`, `useTaskCounters`, `NotificationBell`, `CreateModal`, `ErrorAlert`, `roleLabel`, `userInitials`.
- Produces: `header.topbar` (role `banner`) containing the menu button (`aria-label="Меню"`, `aria-expanded`, `aria-controls="app-menu"`), the brand link, the demo badge, the bell, `a.profile-link` and `button.logout-button` (`aria-label="Выйти"`); `aside#app-menu.sidebar` (class `mobile-open` when open) containing `nav` with one `div.nav-group[role=group]` per group, labelled by its `div.nav-group-label` (not a heading: page tests and screen-reader outlines list the page's own h2s, and menu labels must not join them).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/Layout.test.tsx` (extend imports with `fireEvent, within` and `sessionFixture`):

```tsx
describe("shell", () => {
  it("keeps «Выйти» and the profile link in the top bar", async () => {
    mockApi();
    renderApp("/");
    const banner = await screen.findByRole("banner");
    expect(within(banner).getByRole("button", { name: "Выйти" })).toBeTruthy();
    expect(within(banner).getByRole("link", { name: /Анна Петрова/ })).toBeTruthy();
  });

  it("labels the menu groups for a supervisor", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-supervisor"]) });
    renderApp("/");
    const nav = await screen.findByRole("navigation");
    for (const name of ["Работа", "Анализ", "Данные клиентов", "Администрирование"]) {
      expect(within(nav).getByRole("group", { name })).toBeTruthy();
    }
  });

  it("opens and closes the phone menu with the menu button and Escape", async () => {
    mockApi();
    renderApp("/");
    const button = await screen.findByRole("button", { name: "Меню" });
    const menu = document.getElementById(button.getAttribute("aria-controls")!)!;
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(menu.className).toContain("mobile-open");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(menu.className).not.toContain("mobile-open");
  });
});
```

The two existing demo-label tests stay unchanged: both texts remain on the page when `VITE_DEMO_MODE` is `"true"` and absent otherwise.

Update two existing tests for the single avatar (it now sits inside the profile link; the sidebar copy is gone):
- `frontend/src/app/App.test.tsx`, «topbar account avatar»: `header?.querySelector("a.avatar")` → `header?.querySelector("a.profile-link")`.
- `frontend/src/app/auth.test.tsx`, «csrf and permissions»: `expect(screen.getAllByText("АП")).toHaveLength(2);` → `expect(screen.getAllByText("АП")).toHaveLength(1);` with the comment `// One avatar: the initials inside the top-bar profile link.`

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/app/Layout.test.tsx src/app/App.test.tsx`
Expected: FAIL — «Выйти» is in the sidebar, not the banner; no `group` roles; no `aria-expanded` on «Меню»; the App tests from Task 5 fail on `group`.

- [ ] **Step 3: Rewrite the shell markup**

In `frontend/src/app/Layout.tsx`:

1. Change the lucide import to `import { ChevronRight, GraduationCap, LogOut, Menu, Plus } from "lucide-react";` and `import { useEffect, useState } from "react";`.
2. Replace `visiblePages,` in the navigation import with `navGroups,`.
3. After `const closeMenu = () => setMenu(false);` add:

```tsx
  // Escape closes the phone menu.
  useEffect(() => {
    if (!menu) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [menu]);
  const navigate = () => {
    closeMenu();
    setNavResets((n) => n + 1);
  };
```

4. Replace the returned `<div className="app-shell">…</div>` (up to, not including, `{create && …}`) with:

```tsx
      <div className="app-shell">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            aria-label="Меню"
            aria-expanded={menu}
            aria-controls="app-menu"
            onClick={() => setMenu(!menu)}
          >
            <Menu size={20} aria-hidden="true" />
          </button>
          <Link to={paths.overview} className="brand" onClick={closeMenu}>
            <span className="brand-mark" aria-hidden="true">
              <GraduationCap size={20} />
            </span>
            <span className="brand-text">
              <span>UniCRM</span>
              {brand.data?.name && <small className="brand-org">{brand.data.name}</small>}
            </span>
          </Link>
          {inSettings && (
            <div className="breadcrumbs">
              <span>Настройки</span>
              <ChevronRight size={15} aria-hidden="true" />
              <strong>{page?.name ?? NOT_FOUND_TITLE}</strong>
            </div>
          )}
          <div className="topbar-right">
            {isDemoMode && <span className="demo-badge">Демонстрационный контур</span>}
            <NotificationBell />
            <Link to={paths.settingsProfile} className="profile-link" onClick={closeMenu}>
              <span className="avatar" aria-hidden="true">{initials}</span>
              <span className="profile-text">
                <strong>{user.full_name || user.email}</strong>
                <small>{roleLabel(user.roles)}</small>
              </span>
            </Link>
            <button
              className="icon-button logout-button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending || logout.isSuccess}
              aria-label="Выйти"
              title="Выйти"
            >
              <LogOut size={20} aria-hidden="true" />
            </button>
          </div>
        </header>
        <aside id="app-menu" className={menu ? "sidebar mobile-open" : "sidebar"}>
          <nav aria-label="Разделы">
            {navGroups(user.roles).map((g) => (
              <div key={g.id} className="nav-group" role="group" aria-labelledby={`nav-group-${g.id}`}>
                <div className="nav-group-label" id={`nav-group-${g.id}`}>{g.label}</div>
                {g.pages.map((p) => (
                  <NavLink
                    key={p.path}
                    to={p.path}
                    end={p.path === paths.overview}
                    className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
                    onClick={navigate}
                  >
                    <p.icon size={20} aria-hidden="true" />
                    {p.name}
                    {p.path === paths.tasks && openTasks !== undefined && (
                      <span
                        className={overdueTasks > 0 ? "nav-count nav-count-alert" : "nav-count"}
                        title={overdueTasks > 0 ? `Открытых: ${openTasks}, просрочено: ${overdueTasks}` : `Открытых: ${openTasks}`}
                      >
                        {openTasks}
                      </span>
                    )}
                  </NavLink>
                ))}
                {g.hasSettings && (
                  <SettingsMenu
                    pages={settingsPages}
                    currentPath={location.pathname}
                    userRoles={user.roles}
                    onNavigate={navigate}
                  />
                )}
              </div>
            ))}
          </nav>
        </aside>
        {menu && <div className="menu-backdrop" aria-hidden="true" onClick={closeMenu} />}
        <div className="main-shell">
          <main>
            <div className="page-heading">
              <div>
                <h1>{page?.heading ?? NOT_FOUND_TITLE}</h1>
              </div>
              {createKind && canCreate && (
                <button className="primary" onClick={() => setCreate(createKind)}>
                  <Plus size={18} aria-hidden="true" />
                  {CREATE_LABELS[createKind]}
                </button>
              )}
            </div>
            {logout.error && <ErrorAlert error={logout.error} />}
            <Outlet key={`${location.pathname}#${navResets}`} />
            <footer>
              UniCRM {isDemoMode && <span>Рабочий шаблон · Данные вымышлены</span>}
            </footer>
          </main>
        </div>
      </div>
```

(The `<Outlet key>` comment block from the old markup is kept above `<Outlet>` unchanged. The sidebar-bottom block with the note and the profile is removed: its note becomes `demo-badge`, its profile and «Выйти» moved to the top bar.)

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/app`
Expected: PASS — Layout, App (including the Task 5 changes), auth (`getByRole("button", { name: "Выйти" })` still unique), brand.

- [ ] **Step 5: Run the whole suite, types and lint**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npx eslint .`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/Layout.tsx frontend/src/app/Layout.test.tsx frontend/src/app/App.test.tsx frontend/src/app/auth.test.tsx
git commit -m "Move profile and «Выйти» to the top bar and group the side menu"
```

### Task 7: Shell styles

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/styles.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
  const rule = (selector: string) =>
    withoutComments(rules).match(new RegExp(`(?:^|\\n)${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`))?.[1] ?? "";

  it("lets the side menu scroll so its last entries stay reachable on short screens", () => {
    expect(rule(".sidebar")).toMatch(/overflow-y:\s*auto/);
  });

  it("turns the side menu into a drawer below 1280px", () => {
    expect(withoutComments(rules)).toMatch(/@media \(max-width: 1279px\)\s*\{[^@]*\.sidebar\s*\{[^}]*transform:\s*translateX\(-100%\)/);
  });

  it("gives menu items and the top-bar buttons at least 44px", () => {
    expect(withoutComments(rules)).toMatch(/(?:^|\n)\.nav-item,\s*\.nav-subitem\s*\{[^}]*min-height:\s*44px/);
    expect(rule(".topbar .icon-button")).toMatch(/width:\s*var\(--atmr-size-l\)/);
  });

  it("has no hover flyout styles left", () => {
    expect(css).not.toMatch(/\.settings-menu-panel/);
  });
```

Replace the existing test `gives the organization line in the dark sidebar the sidebar's muted colour (readable contrast)` (its `.sidebar .brand-org` rule is deleted below) with:

```ts
  it("shows the organization line under UniCRM in the soft text colour", () => {
    expect(rule(".brand-org")).toMatch(/color:\s*var\(--atmr-fg-soft\)/);
  });
```

(If the bug-fix branch was merged, its `lets the fixed sidebar scroll…` test duplicates the first one; delete the older one.)

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/styles.test.ts`
Expected: FAIL on the drawer breakpoint, 44 px rules and (if not merged) sidebar overflow.

- [ ] **Step 3: Replace the shell rules**

Delete these rule blocks from `styles.css`: `.app-shell`, `.sidebar`, `.brand`, `.brand-mark`, `.brand-text` and children, `.nav-label`, `.nav-item`, `.nav-item:hover`, `.nav-item.active`, `.nav-count`, `.nav-count-alert`, `.sidebar-bottom`, `.sidebar-note` and children, `.status-dot` (if only used by the note), `.profile`, `.profile-link` and children, `.logout-button`, `.main-shell`, `.topbar`, `.topbar-right` and children, `.breadcrumbs` (top-bar one), `.sidebar .brand-org`, and the `.sidebar`, `.brand`, `.brand-sub`, `.main-shell`, `.topbar` overrides inside `@media (max-width: 1200px)` and `@media (max-width: 800px)`. Keep every non-shell rule in those media blocks. Then add:

```css
/* ——— Shell: top bar, side menu, phone drawer (spec §3.1) ——— */
.app-shell {
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr);
  grid-template-rows: 64px 1fr;
  min-height: 100vh;
}
.topbar {
  grid-column: 1 / -1;
  position: sticky;
  top: 0;
  z-index: var(--atmr-z-index-sticky);
  display: flex;
  align-items: center;
  gap: var(--atmr-spacing-4x);
  padding: 0 var(--atmr-spacing-6x);
  background: var(--atmr-bg-surface1);
  border-bottom: 1px solid var(--atmr-border-soft);
}
.topbar .icon-button {
  width: var(--atmr-size-l);
  height: var(--atmr-size-l);
}
.menu-button {
  display: none;
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--atmr-spacing-3x);
  color: var(--atmr-fg-default);
  text-decoration: none;
  font: var(--atmr-font-heading-h3);
  min-height: 44px;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--atmr-border-radius-m);
  background: var(--atmr-accent-default);
  color: var(--atmr-accent-on-accent);
}
.brand-text {
  display: flex;
  flex-direction: column;
}
.brand-org {
  font: var(--atmr-font-description-l);
  color: var(--atmr-fg-soft);
}
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: var(--atmr-spacing-2x);
  font: var(--atmr-font-body-s);
  color: var(--atmr-fg-soft);
}
.breadcrumbs strong {
  color: var(--atmr-fg-default);
  font-weight: 500;
}
.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--atmr-spacing-2x);
}
.demo-badge {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 var(--atmr-spacing-2x);
  border-radius: var(--atmr-border-radius-xs);
  background: var(--atmr-warning-container-default);
  color: var(--atmr-warning-800);
  font: var(--atmr-font-description-l-strong);
}
.profile-link {
  display: flex;
  align-items: center;
  gap: var(--atmr-spacing-3x);
  min-height: 44px;
  padding: 0 var(--atmr-spacing-2x);
  border-radius: var(--atmr-border-radius-m);
  color: var(--atmr-fg-default);
  text-decoration: none;
}
.profile-link:hover {
  background: var(--atmr-neutral-container-default);
}
.profile-text {
  display: flex;
  flex-direction: column;
  font: var(--atmr-font-body-s-strong);
}
.profile-text small {
  font: var(--atmr-font-description-l);
  color: var(--atmr-fg-soft);
}
.sidebar {
  position: sticky;
  top: 64px;
  height: calc(100vh - 64px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--atmr-spacing-4x) var(--atmr-spacing-3x);
  background: var(--atmr-bg-surface2);
  border-right: 1px solid var(--atmr-border-soft);
}
.nav-group + .nav-group {
  margin-top: var(--atmr-spacing-4x);
}
.nav-group-label {
  margin: 0 var(--atmr-spacing-3x) var(--atmr-spacing-1x);
  font: var(--atmr-font-description-l-strong);
  color: var(--atmr-fg-soft);
}
.nav-item,
.nav-subitem {
  display: flex;
  align-items: center;
  gap: var(--atmr-spacing-3x);
  width: 100%;
  min-height: 44px;
  padding: 0 var(--atmr-spacing-3x);
  border: 0;
  border-radius: var(--atmr-border-radius-m);
  background: transparent;
  color: var(--atmr-fg-default);
  font: var(--atmr-font-body-s-strong);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.nav-subitem {
  padding-left: var(--atmr-spacing-10x);
  font: var(--atmr-font-body-s);
}
.nav-item:hover,
.nav-subitem:hover {
  background: var(--atmr-neutral-container-default);
}
.nav-item.active,
.nav-subitem.active {
  background: var(--atmr-accent-container-default);
  color: var(--atmr-accent-active);
}
.nav-count {
  margin-left: auto;
  padding: 2px var(--atmr-spacing-2x);
  border-radius: var(--atmr-border-radius-full);
  background: var(--atmr-neutral-container-default);
  font: var(--atmr-font-description-l-strong);
}
.nav-count-alert {
  background: var(--atmr-error-container-default);
  color: var(--atmr-error-700);
}
.settings-group-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.settings-group-chevron {
  margin-left: auto;
  transition: transform var(--atmr-motion-duration-s) var(--atmr-motion-easing-productive-standard);
}
.nav-item[aria-expanded="true"] .settings-group-chevron {
  transform: rotate(180deg);
}
.main-shell {
  min-width: 0;
}
.menu-backdrop {
  display: none;
}
@media (max-width: 1279px) {
  .app-shell {
    grid-template-columns: minmax(0, 1fr);
  }
  .menu-button {
    display: inline-grid;
    place-items: center;
  }
  .sidebar {
    position: fixed;
    left: 0;
    top: 64px;
    width: 300px;
    z-index: var(--atmr-z-index-overlay);
    transform: translateX(-100%);
    visibility: hidden;
    transition: transform var(--atmr-motion-duration-s) var(--atmr-motion-easing-productive-standard), visibility 0s linear var(--atmr-motion-duration-s);
    box-shadow: var(--atmr-shadow-bottom-m);
  }
  .sidebar.mobile-open {
    transform: translateX(0);
    visibility: visible;
    transition: transform var(--atmr-motion-duration-s) var(--atmr-motion-easing-productive-standard);
  }
  .menu-backdrop {
    display: block;
    position: fixed;
    inset: 64px 0 0 0;
    z-index: calc(var(--atmr-z-index-overlay) - 1);
    background: var(--crm-overlay);
  }
}
@media (max-width: 767px) {
  .topbar {
    padding: 0 var(--atmr-spacing-2x);
    gap: var(--atmr-spacing-1x);
  }
  .brand-org,
  .profile-text,
  .demo-badge,
  .breadcrumbs {
    display: none;
  }
}
```

(`visibility: hidden` keeps the closed drawer's links out of the Tab order.)

- [ ] **Step 4: Run tests, types, lint and build**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npx eslint . && npx vite build`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles.css frontend/src/styles.test.ts
git commit -m "Restyle the shell: light scrolling side menu, top bar, drawer below 1280px"
```

### Task 8: Token documentation and Stage 1 verification

**Files:**
- Modify: `docs/design/tokens.md` (rewrite)

- [ ] **Step 1: Rewrite `docs/design/tokens.md`**

Replace it with: the source (Storybook Purple light, read 28 Sep 2026), the colour, typography, space, radius, shadow, motion and layer tables from spec §2 (copy them verbatim), the `--crm-*` overrides with their reasons, the legacy-alias table from Task 2 with the note "aliases are removed in Stage 5", and the rules "no text below 12 px; routine data ≥ 14 px; phone targets ≥ 44 px; status text uses the -700/-800/-600 steps".

- [ ] **Step 2: Commit**

```bash
git add docs/design/tokens.md
git commit -m "Document the Rostelecom token layer"
```

- [ ] **Step 3: Bring up the isolated stack from the branch**

From the worktree root (copy `deploy/local/api.env` and `keycloak.env` from the main checkout into the worktree's gitignored `deploy/local/`, mode 600):

```bash
docker compose -p edu-crm-verify -f compose.yaml -f <scratchpad>/verify/verify.override.yaml up -d --build db keycloak-db-init keycloak api web
# wait for http://localhost:18080/auth/realms/edu-crm/.well-known/openid-configuration → 200
COMPOSE_PROJECT_NAME=edu-crm-verify bash scripts/keycloak-add-public-origin.sh http://localhost:18080
# set random throwaway passwords for irina_super_admin, admin_1, manager_1 with kcadm (requiredActions=[]),
# written only to deploy/local/verify-accounts.env (mode 600), never printed
```

Expected: `api`, `db`, `keycloak`, `web` healthy; production's five containers untouched.

- [ ] **Step 4: Run the audit for every role**

```bash
cd frontend
P=/,/universities,/universities/1,/contracts,/interactions,/interactions/board,/interactions/1,/tasks,/tasks/1,/tasks/templates,/analytics,/reports,/catalogs,/vendors,/learners,/applications,/customer-imports,/fraud-alerts,/imports,/workflows,/settings/profile,/settings/organization,/settings/universities,/settings/notifications,/settings/security,/settings/users,/settings/personal-data,/settings/backups
for r in super admin manager; do AUDIT_ACCOUNTS=../deploy/local/verify-accounts.env npm run audit:ui -- --role $r --pages $P --out ../../ui-audit/after-stage1; done
```

Expected for Stage 1: `menuReach` true everywhere; no `pageOverflowX`; no text under 12 px. Phone tap-target findings inside page content are expected until Stage 2 (controls) and are listed, not fixed, in the report; findings in the shell (top bar, menu) must be zero.

- [ ] **Step 5: Manual keyboard and touch pass**

At 1440×900 and 375×812: Tab from the top reaches the menu button, brand, bell, profile, «Выйти», every menu entry and «Настройки»; Enter opens «Настройки»; Esc closes the phone drawer; a touch tap on «Настройки» opens it (Playwright context with `hasTouch: true`, `page.tap`). Sign out from 1280×600 and confirm `/api/v1/auth/me` returns 401.

- [ ] **Step 6: Tear down**

```bash
docker compose -p edu-crm-verify -f compose.yaml down -v --rmi local
rm -f deploy/local/verify-accounts.env deploy/local/api.env deploy/local/keycloak.env
```

Expected: no `edu-crm-verify` containers or volumes; production still running.

- [ ] **Step 7: Report and stop**

Report progress to the owner: commits, test counts, audit summary before/after per role, open findings for Stage 2, and anything not verified. Continue to Stage 2 (owner decision); keep the isolated stack for later stages or recreate it.

---

## Stage 2 — Common controls

**Scope:** buttons (`primary`, `secondary`, `danger`, `text-button`, `icon-button`), inputs, native selects and date fields (restyled, still native), textareas, checkboxes and switches with 44 px hit areas, chips (`filter-pill`), segmented view switches, tags and badges (stage colour dot + text), inline notifications (`ErrorAlert`, `QueryState`), toasts, tables (`data-table`, `table-wrap`: size M, sticky header, framed horizontal scroll), pagination, dialogs (`Modal.tsx`: focus trap, Esc, backdrop), empty and loading states, field hints and errors (`field-hint`, `field-error` with `aria-describedby`).
**Acceptance:** every class listed restyled with `--atmr-*`/`--crm-*` tokens only; the audit reports zero phone controls under 44 px across all pages; no text below AA; all existing tests pass; before/after screenshots.

**Approach:** the shared rules are replaced where they are defined today (base elements, `.primary`/`.secondary`/`.danger`/`.text-button`/`.icon-button`, fields, `table`/`th`/`td`, `.badge*`, `.error`, `.empty`/`.loading`, `dialog`/`.modal`, `.tabs`/`.tab`, `.chip`, `.pagination`, `.field-error`/`.field-hint`), keeping class names so no page markup changes except where noted. Page-specific rules are left to Stage 3.

**Tasks:**
1. *Guards first* (`styles.test.ts`): focus = 2 px accent outline with 2 px offset; `html` has `scroll-padding-top` ≥ the top bar; no `font-size: 0` anywhere (the phone create button keeps its label); table cells 14 px `--atmr-fg-default`, headers 14 px `--atmr-fg-soft`; phone rules give buttons, icon buttons, chips, tabs, pagination buttons and fields at least 44 px, and fields 16 px text (no iOS zoom).
2. *Buttons and links* — primary / secondary / outline / danger / text; `.page-heading .primary` 48 px; M 36 px elsewhere on desktop; 44 px on phones; disabled state without `cursor: wait`.
3. *Fields* — inputs, selects (custom chevron), textareas: 40 px desktop (`--atmr-size-m-chip`), 44 px phone, 1 px `--crm-input-border`, 8 px radius, 14/16 px text, focus border accent, placeholders `--atmr-fg-muted`; checkboxes and radios `accent-color`, 44 px label hit area on phones.
4. *Tables* — size M, header `bg-surface2`, row dividers `border-muted`, row hover `accent-container-soft`, numbers right-aligned where marked.
5. *Tags and badges* — neutral container, stage/status dot + 14 px text.
6. *Feedback* — `.error` as an error inline notification (icon, text, retry), `.loading` with `role="status"` and a 300 ms delayed fade-in (no flash), `.empty` with body text; `dialog` 12 px radius, `--crm-overlay` backdrop.
7. *Tabs, chips, pagination* — tabs with an accent underline, chips as pills with `aria-pressed` styling, pagination 36/44 px.
8. *Verify* — full suite, type check, lint, build, audit (phone tap targets in shared controls must be zero; remaining page-specific findings go to Stage 3).

**Rulings (28 Sep 2026):** fields are 40 px on desktop instead of the spec's 48 px (the Storybook's 40 px `size-m-chip` step) because 48 px fields made dense filter bars and table toolbars too tall for a working register; phones stay at 44 px. Field borders are 1 px `--atmr-neutral-400` (4.06:1, meets 3:1) instead of 2 px, which read too heavy at that density.

## Stage 3 — Daily workflows

**Scope:** Overview (figures strip, «Ближайшие задачи», «Программы в работе», «Последние действия», demo chart labelled), Universities list and detail (existing columns and actions only), Contracts, Interactions register as the default view with the stage board one click away, Interaction detail with status timeline, Tasks (list, deadlines, planner, filters, bulk actions) and Task detail. Body text rises to 16 px here; tables stay 14 px. Phone layouts use stacked rows for the main lists.
**Acceptance:** each role completes: create an interaction, change its stage, add a task, complete a task, open a university and its interactions, add a contract; no lost actions (compare the action inventory before/after); audit clean.

## Stage 3S — Settings (brought forward from Stage 5 by owner decision)

**Scope:** Личный профиль (with sender addresses and phone verification), Организация, Уведомления, Безопасность, Резервное копирование; plus the shared Settings frame (heading, the in-menu «Настройки» group from Stage 1). Pages keep every field, action, permission check and server call; superadmin-only content (users, backups) stays gated.

**Tasks:**
1. **Settings frame** — one layout for all Settings pages: page heading with a one-line purpose, sections with h2 + description + divider (no nested cards), max content width 880 px for forms, a 44 px tap target for every control below 768 px.
2. **Forms** — labels above fields, hints, inline errors via `aria-describedby`, a focusable error summary after a failed save (ui-ux-pro-max), save button state (idle / saving / saved) and a success toast; unsaved changes warning only where the page already tracks dirtiness.
3. **Профиль** — fields grouped «Имя», «Контакты», «Мессенджеры», «Часовой пояс»; phone verification and sender addresses as their own sections with their current states (pending / confirmed / approved / rejected) shown as tags with text.
4. **Организация** — sections for requisites and contacts; read-only view for roles that cannot edit (current rule kept).
5. **Уведомления** — event types grouped as today, each with a visible label and description; the pause control shows its end time and a «Возобновить» action; preference saves confirmed.
6. **Безопасность** — sessions list as a table (stacked rows on phones) with device, IP, last activity and a clearly labelled end-session action with confirmation; login history table; password policy as a read-only list; the messages for shared / not-ended Keycloak sessions kept.
7. **Резервное копирование** — last run status as an inline notification (success / running / failed with stage), history table with «Проверена» tag in `success-700`, the manual backup button with its requested → running → done states and the existing 409 message.
8. **States** — each page: loading (skeleton rows), empty (sentence + next action), error (what failed + retry), permission denied (existing message).

**Tests:** every existing Settings test keeps passing; new tests for the error summary focus, the pause end-time text, the end-session confirmation, the backup status notification variants and each empty/error state.

**Acceptance:** audit clean on all Settings pages for superadmin, admin and manager at 375/768/1024/1440 px; keyboard pass of each form; permissions unchanged (superadmin-only pages and actions still hidden and refused).

## Notifications — end-to-end verification (isolated stack only)

On `edu-crm-verify` with the `notifications` profile (the `notifier` service) running:
1. Trigger an event for a recipient (e.g. the supervisor assigns a task to `manager_1`) and confirm, as `manager_1`, the notification appears in the bell, the unread count increments, and «прочитать» / «прочитать все» clear it (API and UI).
2. Turn that event type off in `manager_1`'s preferences, repeat the trigger, confirm no new notification; turn it back on.
3. Pause notifications until a time in the future, trigger, confirm nothing is created or shown during the pause and the Settings page shows the pause end; resume.
4. Scheduled reminder: create a task due within the reminder window, run one notifier pass, confirm exactly one reminder appears and a second pass does not duplicate it.
5. Record which of these were verified on production (expected: none by Claude — production sign-in is not used; the production notifier's recent passes created 0 notifications).

## Delivery after Stages 1–3 and 3S

Push `ai/redesign-stages-1-3` and open a **draft** PR to `main` with: before/after screenshots (shell, Overview, Universities, Interactions, Tasks, Settings pages at 1440 and 375 px), test counts, audit summary per role, notifications verification results, remaining issues, and a deployment checklist. Do not merge or deploy.

## Stage 4 — Analytics, reports and the remaining pages

**Scope:** Analytics with its agreed structure (period and university filter, «Вузы по этапам», «Внедрённые программы по месяцам», «Рейтинг вузов» top 5, «Скачать PDF»); charts with one-line summaries, direct labels and a second-series pattern; Reports with filters, column choice and xlsx/xls/PDF/JSON downloads; Catalogs, Companies, Learners, Applications, Customer imports, Fraud alerts, Imports, Workflows (drag and drop kept on `@dnd-kit`), Task plan templates.
**Acceptance:** PDF/JSON/xlsx/xls exports byte-for-byte unaffected (compare a download before/after on the isolated stack); demo figures labelled; audit clean.

## Stage 5 — Settings, sign-in and clean-up

**Scope:** the remaining Settings pages (universities, users and roles, personal data, account; the five main ones are in Stage 3S), the in-app sign-in and logged-out screens («Войти через Keycloak»), the Keycloak login theme (spec §7: theme folder, compose mount, `scripts/keycloak-set-login-theme.sh`, realm `loginTheme`, Russian messages, pages: sign-in, update password, reset password, error, logout confirm), removal of all legacy token aliases, final `docs/design/tokens.md`.
**Acceptance:** Keycloak pages screenshotted at 375 and 1440 px on the isolated stack, keyboard-only sign-in works, rollback tested (theme switched back); no legacy alias left (`styles.test.ts` guard); full audit clean for all roles; release checklist with rollback written; **separate owner approval before publishing**.
