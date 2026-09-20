/**
 * Deadline-bucket math for the "Сроки" board — mirrors the backend's `week_bounds()`/`apply_filters()`
 * deadline-preset clauses (task_routes.py) exactly, including the D-172 edge case where "this week"
 * is an empty range on the one day it's Sunday (the week's own last day). Dates are plain ISO
 * (`YYYY-MM-DD`) strings throughout — comparing them lexicographically is equivalent to comparing them
 * chronologically, which sidesteps timezone conversion entirely.
 */

export type DeadlineColumnKey = "overdue" | "today" | "this_week" | "next_week" | "later" | "no_deadline";

/** The board's 6 mandatory columns, always shown in this order even when empty (D-205). */
export const DEADLINE_SYSTEM_COLUMNS: { key: DeadlineColumnKey; label: string }[] = [
  { key: "overdue", label: "Просрочены" },
  { key: "today", label: "Сегодня" },
  { key: "this_week", label: "На этой неделе" },
  { key: "next_week", label: "На следующей неделе" },
  { key: "later", label: "Позже" },
  { key: "no_deadline", label: "Без срока" },
];

function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(d: Date, days: number): Date {
  const next = new Date(d);
  next.setDate(next.getDate() + days);
  return next;
}

/** Monday of the week containing `d` (JS getDay() is Sunday=0..Saturday=6; converted to
 * Python's weekday()-style Monday=0..Sunday=6 before subtracting). */
function mondayOf(d: Date): Date {
  const diff = (d.getDay() + 6) % 7;
  return addDays(d, -diff);
}

/** Sunday of the week containing `d` — the backend's `week_end`. */
function weekEnd(d: Date): Date {
  return addDays(mondayOf(d), 6);
}

/**
 * Resolves the board's full column order: a saved order (system codes mixed with `custom:<id>` refs)
 * is kept as-is except that any of the 6 mandatory system columns missing from it is appended at the
 * end — this board never hides a system column, unlike the planner's `planner_columns` (D-180). With
 * nothing saved yet, the result is just the 6 system columns in their default order.
 */
export function resolveDeadlineColumnOrder(saved: string[] | null | undefined): string[] {
  const systemKeys = DEADLINE_SYSTEM_COLUMNS.map((c) => c.key);
  if (!saved?.length) return [...systemKeys];
  const known = new Set<string>(systemKeys);
  const seen = new Set<string>();
  const order: string[] = [];
  for (const id of saved) {
    if (seen.has(id)) continue;
    if (known.has(id) || id.startsWith("custom:")) {
      order.push(id);
      seen.add(id);
    }
  }
  for (const key of systemKeys) {
    if (!seen.has(key)) order.push(key);
  }
  return order;
}

/** Which of the 6 system columns a task's deadline falls into "today". */
export function classifyDeadline(deadline: string | null, today: Date): DeadlineColumnKey {
  if (!deadline) return "no_deadline";
  const todayIso = toISODate(today);
  if (deadline < todayIso) return "overdue";
  if (deadline === todayIso) return "today";
  const endIso = toISODate(weekEnd(today));
  if (deadline <= endIso) return "this_week";
  const nextEndIso = toISODate(addDays(weekEnd(today), 7));
  if (deadline <= nextEndIso) return "next_week";
  return "later";
}

/**
 * The date prefilled into the task-creation form when it's opened from a column's "+" button, per the
 * owner's exact mapping: yesterday / today / end of this week / end of next week / first day after
 * next week / no date at all.
 */
export function prefillDateForColumn(key: DeadlineColumnKey, today: Date): string | null {
  switch (key) {
    case "overdue":
      return toISODate(addDays(today, -1));
    case "today":
      return toISODate(today);
    case "this_week":
      return toISODate(weekEnd(today));
    case "next_week":
      return toISODate(addDays(weekEnd(today), 7));
    case "later":
      return toISODate(addDays(weekEnd(today), 8));
    case "no_deadline":
      return null;
  }
}
