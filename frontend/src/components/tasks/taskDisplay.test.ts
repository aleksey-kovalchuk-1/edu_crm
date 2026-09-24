import { describe, expect, it } from "vitest";
import { deadlineInfo, nextSort, ruPlural } from "./taskDisplay";

const today = new Date(2026, 8, 24); // 24 Sep 2026, local time

describe("ruPlural", () => {
  it.each([
    [1, "день"], [2, "дня"], [4, "дня"], [5, "дней"], [11, "дней"], [12, "дней"], [14, "дней"],
    [21, "день"], [22, "дня"], [25, "дней"], [101, "день"], [111, "дней"],
  ])("%i → %s", (n, word) => {
    expect(ruPlural(n, "день", "дня", "дней")).toBe(word);
  });
});

describe("deadlineInfo", () => {
  it("marks an open overdue task as danger with how long ago it was due", () => {
    expect(deadlineInfo("2026-09-20", "in_progress", today)).toMatchObject({ label: "Просрочена на 4 дня", tone: "danger" });
    expect(deadlineInfo("2026-09-23", "new", today)).toMatchObject({ label: "Просрочена на 1 день", tone: "danger" });
  });

  it("uses today / tomorrow / in N days for the coming week", () => {
    expect(deadlineInfo("2026-09-24", "new", today)).toMatchObject({ label: "Сегодня", tone: "warning" });
    expect(deadlineInfo("2026-09-25", "new", today)).toMatchObject({ label: "Завтра", tone: "warning" });
    expect(deadlineInfo("2026-09-29", "new", today)).toMatchObject({ label: "Через 5 дней", tone: "neutral" });
  });

  it("shows a plain date further out, and always keeps the full date in the title", () => {
    const far = deadlineInfo("2026-10-15", "new", today);
    expect(far.tone).toBe("neutral");
    expect(far.label).not.toMatch(/Через/);
    expect(far.title).toMatch(/2026/);
  });

  it("never flags finished tasks, however old the deadline", () => {
    expect(deadlineInfo("2026-09-01", "completed", today).tone).toBe("muted");
    expect(deadlineInfo("2026-09-01", "cancelled", today).tone).toBe("muted");
  });

  it("handles a missing deadline", () => {
    expect(deadlineInfo(null, "new", today)).toMatchObject({ label: "Без срока", tone: "muted" });
  });
});

describe("nextSort", () => {
  it("starts a field in its natural direction and flips it on the next click", () => {
    expect(nextSort("-created_at", "deadline")).toBe("deadline");
    expect(nextSort("deadline", "deadline")).toBe("-deadline");
    expect(nextSort("-deadline", "deadline")).toBe("deadline");
  });

  it("starts priority and last change descending (most urgent / most recent first)", () => {
    expect(nextSort("-created_at", "priority")).toBe("-priority");
    expect(nextSort("-priority", "priority")).toBe("priority");
    expect(nextSort("title", "updated_at")).toBe("-updated_at");
  });
});
