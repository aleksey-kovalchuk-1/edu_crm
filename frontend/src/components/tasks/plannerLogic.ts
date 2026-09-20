import { NEXT_STATUSES, type TaskListItem, type TaskStatus } from "../../api/tasks";
import { bucketTasksByColumn, orderColumnCards } from "./boardColumns";

export type PlannerColumns = Record<string, TaskListItem[]>;

/** Buckets tasks by column: a task goes to its custom-column override when one is recorded (and that
 * column is still visible), otherwise to the system column matching its real status — dropped
 * entirely if that status isn't currently visible (D-180; not lost, the List/Deadline views still show
 * it). Thin wrapper over the shared boardColumns.bucketTasksByColumn. */
export function bucketByStatus(
  tasks: TaskListItem[],
  visibleColumns: string[],
  customMembers: Record<string, string> = {},
): PlannerColumns {
  return bucketTasksByColumn(tasks, visibleColumns, customMembers, (t) => t.status);
}

/** Orders a column's cards by the user's saved manual order; cards missing from that order keep the
 * list's original order and are appended after the ones the user has explicitly placed. */
export const orderColumn = orderColumnCards<TaskListItem>;

/** Whether the server's fixed transition table (docs/design/tasks.md) permits this move. Only
 * meaningful between two *system* status columns — moving into/out of a custom column never changes a
 * task's real status (D-203), so callers check `isCustomColumnId` before reaching for this. */
export function isValidMove(from: TaskStatus, to: TaskStatus): boolean {
  return NEXT_STATUSES[from]?.includes(to) ?? false;
}
