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
});
