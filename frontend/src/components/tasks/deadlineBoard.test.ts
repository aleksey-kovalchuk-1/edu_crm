import { describe, expect, it } from "vitest";
import { classifyDeadline, prefillDateForColumn, resolveDeadlineColumnOrder } from "./deadlineBoard";

// 2026-09-23 is a Wednesday: Monday of that week is 2026-09-21, Sunday (week end) 2026-09-27.
const WEDNESDAY = new Date("2026-09-23T12:00:00");
// 2026-09-20 is a Sunday — the week's own last day (mirrors the backend's D-172 boundary case).
const SUNDAY = new Date("2026-09-20T12:00:00");

describe("classifyDeadline", () => {
  it("classifies a null deadline as no_deadline", () => {
    expect(classifyDeadline(null, WEDNESDAY)).toBe("no_deadline");
  });

  it("classifies a past date as overdue", () => {
    expect(classifyDeadline("2026-09-22", WEDNESDAY)).toBe("overdue");
  });

  it("classifies today's date as today", () => {
    expect(classifyDeadline("2026-09-23", WEDNESDAY)).toBe("today");
  });

  it("classifies the rest of the current week (up to and including Sunday) as this_week", () => {
    expect(classifyDeadline("2026-09-25", WEDNESDAY)).toBe("this_week");
    expect(classifyDeadline("2026-09-27", WEDNESDAY)).toBe("this_week");
  });

  it("classifies next Monday through next Sunday as next_week", () => {
    expect(classifyDeadline("2026-09-28", WEDNESDAY)).toBe("next_week");
    expect(classifyDeadline("2026-10-04", WEDNESDAY)).toBe("next_week");
  });

  it("classifies anything after next week as later", () => {
    expect(classifyDeadline("2026-10-05", WEDNESDAY)).toBe("later");
  });

  it("has an empty this_week range when today is itself the week's last day (Sunday)", () => {
    expect(classifyDeadline("2026-09-21", SUNDAY)).toBe("next_week");
  });
});

describe("resolveDeadlineColumnOrder", () => {
  it("defaults to the 6 system columns in order when nothing is saved", () => {
    expect(resolveDeadlineColumnOrder(null)).toEqual([
      "overdue", "today", "this_week", "next_week", "later", "no_deadline",
    ]);
  });

  it("keeps a saved order, including custom columns placed anywhere", () => {
    expect(resolveDeadlineColumnOrder(["overdue", "custom:x", "today", "this_week", "next_week", "later", "no_deadline"])).toEqual([
      "overdue", "custom:x", "today", "this_week", "next_week", "later", "no_deadline",
    ]);
  });

  it("always appends any system column missing from the saved order — the board never hides one", () => {
    expect(resolveDeadlineColumnOrder(["today", "custom:x"])).toEqual([
      "today", "custom:x", "overdue", "this_week", "next_week", "later", "no_deadline",
    ]);
  });

  it("drops duplicate and unknown non-custom entries", () => {
    expect(resolveDeadlineColumnOrder(["today", "today", "bogus"])).toEqual([
      "today", "overdue", "this_week", "next_week", "later", "no_deadline",
    ]);
  });
});

describe("prefillDateForColumn", () => {
  it("maps each system column to the exact date the spec asks for", () => {
    expect(prefillDateForColumn("overdue", WEDNESDAY)).toBe("2026-09-22");
    expect(prefillDateForColumn("today", WEDNESDAY)).toBe("2026-09-23");
    expect(prefillDateForColumn("this_week", WEDNESDAY)).toBe("2026-09-27");
    expect(prefillDateForColumn("next_week", WEDNESDAY)).toBe("2026-10-04");
    expect(prefillDateForColumn("later", WEDNESDAY)).toBe("2026-10-05");
    expect(prefillDateForColumn("no_deadline", WEDNESDAY)).toBeNull();
  });
});
