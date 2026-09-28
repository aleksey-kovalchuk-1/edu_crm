import { describe, expect, it } from "vitest";
import css from "./styles.css?raw";

/* Guards the design-token layer (docs/design/tokens.md): raw values live only in the :root block. */
const rootStart = css.indexOf(":root {");
const rootEnd = css.indexOf("}", rootStart);
const tokens = css.slice(rootStart, rootEnd);
const rules = css.slice(0, rootStart) + css.slice(rootEnd + 1);
const withoutComments = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "");

describe("styles.css design tokens", () => {
  it("reads the real stylesheet", () => {
    expect(rootStart).toBeGreaterThan(-1);
    expect(rules.length).toBeGreaterThan(10_000);
  });

  it("keeps colours in tokens only", () => {
    const raw = withoutComments(rules)
      .replace(/url\([^)]*\)/g, "")
      .match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|:\s*(white|black)\s*;/g);
    expect(raw).toBeNull();
  });

  it("uses the type scale for every font size", () => {
    const sizes = withoutComments(rules).match(/font-size:\s*[^;]+/g) ?? [];
    expect(sizes.filter((s) => !/var\(--text-|:\s*0$/.test(s))).toEqual([]);
  });


  it("shows the organization line under UniCRM in the soft text colour", () => {
    expect(rule(".brand-org")).toMatch(/color:\s*var\(--atmr-fg-soft\)/);
  });
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

  describe("common controls (Stage 2)", () => {
    const clean = withoutComments(rules);
    const phone = [...clean.matchAll(/@media \(max-width: 767px\)\s*\{([\s\S]*?)\n\}/g)].map((m) => m[1]).join("\n");

    it("draws keyboard focus as a 2px accent outline with a 2px gap", () => {
      expect(clean).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--atmr-accent-default\);[^}]*outline-offset:\s*2px;/);
    });

    it("keeps the focused element clear of the sticky top bar", () => {
      expect(rule("html")).toMatch(/scroll-padding-top:\s*80px/);
    });

    it("never hides text with font-size 0 (the phone create button keeps its label)", () => {
      expect(clean).not.toMatch(/font-size:\s*0\s*;/);
    });

    it("sets table cells in 14px default text and headers in 14px soft text", () => {
      expect(rule("td")).toMatch(/font:\s*var\(--atmr-font-body-s\)/);
      expect(rule("td")).toMatch(/color:\s*var\(--atmr-fg-default\)/);
      expect(rule("th")).toMatch(/font:\s*var\(--atmr-font-body-s-strong\)/);
      expect(rule("th")).toMatch(/color:\s*var\(--atmr-fg-soft\)/);
    });

    it("gives shared controls at least 44px on phones", () => {
      expect(phone).toMatch(/\.primary,\s*\.secondary,\s*\.filter,\s*\.filter-pill,\s*\.icon-button,\s*\.text-button,\s*\.tab\s*\{[^}]*min-height:\s*44px/);
      expect(phone).toMatch(/\.icon-button\s*\{[^}]*min-width:\s*44px/);
    });

    it("wraps the page heading on phones so the labelled create button gets its own line", () => {
      expect(phone).toMatch(/\.page-heading\s*\{[^}]*flex-wrap:\s*wrap/);
    });

    it("uses 16px text in phone form fields so iOS does not zoom", () => {
      expect(phone).toMatch(/input:not\(\[type="checkbox"\]\):not\(\[type="radio"\]\):not\(\[type="file"\]\),\s*select:not\(\[multiple\]\),\s*textarea:not\(\[disabled\]\)\s*\{[^}]*font-size:\s*var\(--text-md\);[^}]*min-height:\s*44px/);
    });
  });

  describe("daily workflows (Stage 3)", () => {
    const clean = withoutComments(rules);
    const phone = [...clean.matchAll(/@media \(max-width: 767px\)\s*\{([\s\S]*?)\n\}/g)].map((m) => m[1]).join("\n");

    it("stacks marked tables into labelled rows on phones", () => {
      expect(phone).toMatch(/\.stack-table tr\s*\{[^}]*display:\s*block/);
      expect(phone).toMatch(/\.stack-table td\[data-label\]::before\s*\{[^}]*content:\s*attr\(data-label\)/);
      expect(phone).toMatch(/\.stack-table thead\s*\{[^}]*position:\s*absolute/);
    });

    it("gives page toolbars, task counters and stacked-row titles 44px on phones", () => {
      expect(phone).toMatch(/\.toolbar \.primary,\s*\.toolbar \.secondary,\s*\.toolbar \.filter,\s*\.task-toolbar \.primary,\s*\.scope-select select,\s*\.task-search,\s*\.counter-chip,\s*\.th-sort\s*\{[^}]*min-height:\s*44px/);
      expect(phone).toMatch(/\.stack-table td:first-child a\s*\{[^}]*min-height:\s*44px/);
    });

    it("sets body text at 16px (tables and fields stay at 14px)", () => {
      expect(tokens).toMatch(/--text-base:\s*16px;/);
    });

    it("turns panels into flat frames without shadows", () => {
      expect(rule(".panel")).toMatch(/border:\s*1px solid var\(--atmr-border-soft\)/);
      expect(rule(".panel")).toMatch(/border-radius:\s*var\(--atmr-border-radius-l\)/);
      expect(rule(".panel")).toMatch(/box-shadow:\s*none/);
    });

    it("styles the view switch as a segmented control with a 44px phone size", () => {
      expect(rule(".segmented button")).toMatch(/min-height:\s*var\(--atmr-size-m\)/);
      expect(phone).toMatch(/\.segmented button\s*\{[^}]*min-height:\s*44px/);
    });
  });

  describe("settings (Stage 3S)", () => {
    const clean = withoutComments(rules);
    const phone = [...clean.matchAll(/@media \(max-width: 767px\)\s*\{([\s\S]*?)\n\}/g)].map((m) => m[1]).join("\n");

    it("puts settings labels above their fields", () => {
      expect(clean).toMatch(/\.settings-body label:not\(\.checkbox-row\),\s*\.settings-panel \.wizard-body label:not\(\.checkbox-row\)\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column/);
    });

    it("colours notices with the tone container and the tone's text step", () => {
      expect(rule(".notice-error")).toMatch(/background:\s*var\(--atmr-error-container-default\)/);
      expect(rule(".notice-error")).toMatch(/color:\s*var\(--atmr-error-700\)/);
      expect(rule(".notice-success")).toMatch(/color:\s*var\(--atmr-success-700\)/);
      expect(rule(".notice-warning")).toMatch(/color:\s*var\(--atmr-warning-800\)/);
      expect(rule(".notice-info")).toMatch(/color:\s*var\(--atmr-info-600\)/);
    });

    it("keeps the top bar within the screen on tablets", () => {
      expect(clean).toMatch(/@media \(max-width: 1023px\)\s*\{[^@]*\.profile-text,\s*\.demo-badge\s*\{[^}]*display:\s*none/);
      expect(rule(".breadcrumbs")).toMatch(/min-width:\s*0/);
      expect(phone).toMatch(/\.error button\s*\{[^}]*min-height:\s*44px/);
    });

    it("stacks settings form rows and gives checkbox rows 44px on phones", () => {
      expect(phone).toMatch(/\.form-row\s*\{[^}]*grid-template-columns:\s*1fr/);
      expect(phone).toMatch(/\.checkbox-row\s*\{[^}]*min-height:\s*44px/);
    });
  });

  describe("settings alignment and users table (regression)", () => {
    const clean = withoutComments(rules);

    it("gives every Settings section the same content width, with tables still full width", () => {
      expect(clean).toMatch(/\.settings-body > :not\(\.table-wrap\),\s*\.settings-panel \.wizard-body > :not\(\.table-wrap\)\s*\{[^}]*max-width:\s*880px/);
    });

    it("spaces the rows of forms nested inside a Settings section", () => {
      expect(clean).toMatch(/\.settings-body form:not\(\.role-editor\)\s*\{[^}]*display:\s*flex;[^}]*gap:\s*var\(--atmr-spacing-4x\)/);
    });

    it("left-aligns Settings actions so buttons stay with their fields", () => {
      expect(clean).toMatch(/\.settings-body \.wizard-actions,\s*\.settings-panel \.wizard-actions\s*\{[^}]*justify-content:\s*flex-start/);
    });

    it("lets the users table wrap so long logins and emails never push the role editor off screen", () => {
      expect(rule(".users-table")).toMatch(/white-space:\s*normal/);
      expect(rule(".wrap-anywhere")).toMatch(/overflow-wrap:\s*anywhere/);
      expect(rule(".role-editor")).toMatch(/flex-wrap:\s*wrap/);
    });
  });
});

