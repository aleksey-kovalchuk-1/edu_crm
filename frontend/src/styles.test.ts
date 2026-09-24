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

  it("has no text token smaller than 11px", () => {
    const px = [...tokens.matchAll(/--text-[\w]+:\s*(\d+)px/g)].map((m) => Number(m[1]));
    expect(px.length).toBeGreaterThan(0);
    expect(Math.min(...px)).toBeGreaterThanOrEqual(11);
  });
});
