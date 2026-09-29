import { describe, expect, it } from "vitest";

// The sign-in service's product name is an implementation detail: people see «вход» and «регистрация», not
// «Keycloak». Comments, identifiers and API paths may still name it.
const sources = import.meta.glob(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}", "!../test/**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function visibleText(source: string): string[] {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const literals = [...code.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)].map((m) => m[1] ?? m[2] ?? m[3]);
  const jsxText = [...code.matchAll(/>([^<>{}]+)</g)].map((m) => m[1]);
  return [...literals, ...jsxText].filter((text) => /Keycloak/.test(text));
}

describe("user-visible text", () => {
  it("never names Keycloak", () => {
    const offenders = Object.entries(sources).flatMap(([file, source]) => visibleText(source).map((t) => `${file}: ${t.trim()}`));
    expect(offenders).toEqual([]);
  });
});
