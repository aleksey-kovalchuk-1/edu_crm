import { describe, expect, it } from "vitest";
import {
  addOneYear,
  csvCell,
  formatDate,
  formatDateTime,
  formatNumber,
  formatRelativeTime,
  initials,
  launchCode,
  matches,
  safeWebsiteUrl,
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

  it("formats relative times in Russian", () => {
    const now = Date.parse("2026-09-15T12:00:00Z");
    expect(formatRelativeTime("2026-09-15T11:59:40Z", now)).toBe("только что");
    expect(formatRelativeTime("2026-09-15T12:00:30Z", now)).toBe("только что");
    expect(formatRelativeTime("2026-09-15T11:55:00", now)).toBe("5 мин назад");
    expect(formatRelativeTime("2026-09-15T09:00:00Z", now)).toBe("3 ч назад");
    expect(formatRelativeTime("2026-09-10T09:00:00Z", now)).toMatch(/^10 сент/);
    expect(formatRelativeTime("2025-01-15T09:00:00Z", now)).toMatch(/2025/);
    expect(formatRelativeTime("not a date", now)).toBe("");
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

  it("computes the default licence validity", () => {
    expect(addOneYear("2026-01-15")).toBe("2027-01-15");
    expect(addOneYear("2024-02-29")).toBe("2025-02-28");
    expect(addOneYear("")).toBe("");
  });

  it("allows only http(s) website links", () => {
    expect(safeWebsiteUrl("https://stu.example")).toBe("https://stu.example/");
    expect(safeWebsiteUrl("stu.example")).toBe("https://stu.example/");
    expect(safeWebsiteUrl("javascript:alert(1)")).toBeNull();
    expect(safeWebsiteUrl("ftp://stu.example")).toBeNull();
    expect(safeWebsiteUrl("")).toBeNull();
  });
});
