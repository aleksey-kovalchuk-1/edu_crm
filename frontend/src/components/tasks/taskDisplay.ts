import type { TaskStatus } from "../../api/tasks";
import { formatDate, formatFullDate } from "../../lib/format";

/** Semantic badge class per status — shared by the list and both boards so a status reads the same everywhere. */
export const STATUS_BADGE: Record<TaskStatus, string> = {
  new: "status-badge status-new",
  in_progress: "status-badge status-in-progress",
  awaiting_review: "status-badge status-review",
  completed: "status-badge status-completed",
  deferred: "status-badge status-deferred",
  cancelled: "status-badge status-cancelled",
};

/** Russian plural form for `n`: ruPlural(n, "день", "дня", "дней"). */
export function ruPlural(n: number, one: string, few: string, many: string): string {
  const mod100 = Math.abs(n) % 100;
  const mod10 = mod100 % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

export type DeadlineTone = "danger" | "warning" | "neutral" | "muted";

const DAY_MS = 86_400_000;
const FINISHED: ReadonlySet<TaskStatus> = new Set(["completed", "cancelled"]);

/** Local-midnight date of a server `YYYY-MM-DD` (no timezone shift). */
function localDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/**
 * How a deadline reads in the list: relative for the coming week ("Сегодня", "Через 3 дня"),
 * a plain date further out, and a danger tone only for open tasks past due — the same rule
 * the server's `overdue` preset uses.
 */
export function deadlineInfo(
  deadline: string | null,
  status: TaskStatus,
  today: Date = new Date(),
): { label: string; tone: DeadlineTone; title: string } {
  if (!deadline) return { label: "Без срока", tone: "muted", title: "Срок не задан" };
  const title = `Срок: ${formatFullDate(deadline)}`;
  if (FINISHED.has(status)) return { label: formatDate(deadline), tone: "muted", title };
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const days = Math.round((localDate(deadline).getTime() - start.getTime()) / DAY_MS);
  if (days < 0) {
    const late = -days;
    return { label: `Просрочена на ${late} ${ruPlural(late, "день", "дня", "дней")}`, tone: "danger", title };
  }
  if (days === 0) return { label: "Сегодня", tone: "warning", title };
  if (days === 1) return { label: "Завтра", tone: "warning", title };
  if (days < 7) return { label: `Через ${days} ${ruPlural(days, "день", "дня", "дней")}`, tone: "neutral", title };
  return { label: formatDate(deadline), tone: "neutral", title };
}

/** Fields whose first click sorts descending (most urgent / most recent first). */
const DESC_FIRST = new Set(["priority", "updated_at", "created_at"]);

/** The `sort` value after clicking a column header: a new field starts in its natural direction, the same field flips. */
export function nextSort(current: string, field: string): string {
  const currentField = current.replace(/^-/, "");
  if (currentField === field) return current.startsWith("-") ? field : `-${field}`;
  return DESC_FIRST.has(field) ? `-${field}` : field;
}
