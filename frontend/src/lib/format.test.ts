import { describe, expect, it } from "vitest";
import {
  csvCell,
  formatDate,
  formatDateTime,
  formatNumber,
  initials,
  launchCode,
  matches,
  stageGroup,
  toCsv,
} from "./format";

describe("format helpers", () => {
  it("formats numbers with Russian grouping", () => {
    expect(formatNumber(12345).replace(/\s/g, " ")).toBe("12 345");
  });

  it("formats date-only strings without shifting the day", () => {
    expect(formatDate("2026-03-05")).toMatch(/^5 мар/);
  });

  it("treats zone-less timestamps as UTC", () => {
    expect(formatDateTime("2026-09-15T10:00:00")).toBe(
      new Date("2026-09-15T10:00:00Z").toLocaleString("ru-RU"),
    );
    expect(formatDateTime("2026-09-15T10:00:00+03:00")).toBe(
      new Date("2026-09-15T07:00:00Z").toLocaleString("ru-RU"),
    );
    expect(formatDateTime("2026-09-15T10:00:00-03:00")).toBe(
      new Date("2026-09-15T13:00:00Z").toLocaleString("ru-RU"),
    );
    expect(formatDateTime("2026-09-15T10:00:00.123456z")).not.toBe(
      "Invalid Date",
    );
  });

  it("maps stages to board columns", () => {
    expect([0, 2, 3, 5, 6, 7, 8, 10, 11, 13].map(stageGroup)).toEqual([
      0, 0, 1, 1, 2, 2, 3, 3, 4, 4,
    ]);
  });

  it("builds initials, codes and search matches", () => {
    expect(initials("Ирина Петрова Сергеевна")).toBe("ИП");
    expect(launchCode(7)).toBe("ВЗ-0007");
    expect(matches("Колледж связи Казань", "казань")).toBe(true);
  });

  it("escapes CSV cells and neutralises formulas", () => {
    expect(csvCell('a"b')).toBe('"a""b"');
    expect(csvCell("=SUM(A1)")).toBe(`"'=SUM(A1)"`);
    expect(toCsv([["Год", 2025]])).toBe('﻿"Год";"2025"');
  });
});
