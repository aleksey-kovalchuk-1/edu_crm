import { NEXT_STATUSES, type TaskListItem, type TaskStatus } from "../../api/tasks";

export type PlannerColumns = Partial<Record<TaskStatus, TaskListItem[]>>;

/** Buckets tasks by status into only the visible columns; a task whose status isn't currently visible
 * simply doesn't appear on the board (it's not lost — the List/Deadline views still show it). */
export function bucketByStatus(tasks: TaskListItem[], visibleColumns: TaskStatus[]): PlannerColumns {
  const buckets: PlannerColumns = Object.fromEntries(visibleColumns.map((s) => [s, []]));
  for (const task of tasks) {
    buckets[task.status]?.push(task);
  }
  return buckets;
}

/** Orders a column's cards by the user's saved manual order; cards missing from that order keep the
 * list's original order and are appended after the ones the user has explicitly placed. */
export function orderColumn(tasks: TaskListItem[], order: number[] | undefined): TaskListItem[] {
  if (!order?.length) return tasks;
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const ordered: TaskListItem[] = [];
  for (const id of order) {
    const task = byId.get(id);
    if (task) {
      ordered.push(task);
      byId.delete(id);
    }
  }
  return [...ordered, ...byId.values()];
}

/** Whether the server's fixed transition table (docs/design/tasks.md) permits this move. */
export function isValidMove(from: TaskStatus, to: TaskStatus): boolean {
  return NEXT_STATUSES[from]?.includes(to) ?? false;
}
