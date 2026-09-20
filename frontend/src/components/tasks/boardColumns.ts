import type { CustomColumn } from "../../api/tasks";

/** Custom (personal, user-created) columns are always identified by this prefix, never by their
 * displayed title — titles can be renamed freely without breaking saved positions/membership. */
export const isCustomColumnId = (id: string): boolean => id.startsWith("custom:");

let fallbackCounter = 0;

/** A fresh, stable id for a new custom column. Prefers crypto.randomUUID (available in every real
 * browser this app targets); falls back to a counter for environments without it (e.g. some test
 * runners) since collision-freedom, not cryptographic strength, is all that's needed here. */
function newCustomColumnId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `custom:${crypto.randomUUID()}`;
  }
  fallbackCounter += 1;
  return `custom:${Date.now()}-${fallbackCounter}`;
}

export function addCustomColumn(
  order: string[],
  customColumns: Record<string, CustomColumn>,
  title: string,
): { order: string[]; customColumns: Record<string, CustomColumn> } {
  const id = newCustomColumnId();
  return { order: [...order, id], customColumns: { ...customColumns, [id]: { title } } };
}

export function renameCustomColumn(
  customColumns: Record<string, CustomColumn>,
  id: string,
  title: string,
): Record<string, CustomColumn> {
  return { ...customColumns, [id]: { title } };
}

/**
 * Removes a custom column definition and its order entry; every task explicitly placed in it is
 * dropped from the membership map too (not deleted — it just falls back to rendering in whichever
 * system column matches its real status/deadline, per bucketTasksByColumn below).
 */
export function deleteCustomColumn(
  order: string[],
  customColumns: Record<string, CustomColumn>,
  members: Record<string, string>,
  id: string,
): { order: string[]; customColumns: Record<string, CustomColumn>; members: Record<string, string> } {
  const restColumns = { ...customColumns };
  delete restColumns[id];
  const restMembers = Object.fromEntries(Object.entries(members).filter(([, columnId]) => columnId !== id));
  return { order: order.filter((c) => c !== id), customColumns: restColumns, members: restMembers };
}

/** Moves one column (system or custom) to a new index in the shared order list — the mechanism behind
 * dragging a column header, and behind placing a freshly-created column anywhere among the system ones. */
export function moveColumnId(order: string[], id: string, toIndex: number): string[] {
  const from = order.indexOf(id);
  if (from === -1) return order;
  const next = [...order];
  next.splice(from, 1);
  next.splice(Math.max(0, Math.min(toIndex, next.length)), 0, id);
  return next;
}

/**
 * Buckets tasks into columns: a task goes to its custom-column override (`customMembers`) when one is
 * recorded *and* that column still exists among `columnIds`; otherwise it goes to whatever
 * `naturalColumnOf` derives from the task's own data (real status for the planner, real deadline
 * bucket for the Deadlines board). A task whose natural column isn't currently visible is dropped
 * (matches the planner's existing "hidden column" behaviour); the Deadlines board never hides a system
 * column, so this only matters there for a stale/unknown value.
 */
export function bucketTasksByColumn<T extends { id: number }>(
  tasks: T[],
  columnIds: string[],
  customMembers: Record<string, string>,
  naturalColumnOf: (task: T) => string,
): Record<string, T[]> {
  const buckets: Record<string, T[]> = Object.fromEntries(columnIds.map((id) => [id, []]));
  for (const task of tasks) {
    const override = customMembers[String(task.id)];
    const columnId = override && columnIds.includes(override) ? override : naturalColumnOf(task);
    buckets[columnId]?.push(task);
  }
  return buckets;
}

/** Orders a column's cards by a saved manual order; cards missing from it keep their original relative
 * order and are appended after the ones the user has explicitly placed. Shared by both boards — the
 * planner's own former copy of this (plannerLogic.ts) now just re-exports it. */
export function orderColumnCards<T extends { id: number }>(tasks: T[], order: number[] | undefined): T[] {
  if (!order?.length) return tasks;
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const ordered: T[] = [];
  for (const id of order) {
    const task = byId.get(id);
    if (task) {
      ordered.push(task);
      byId.delete(id);
    }
  }
  return [...ordered, ...byId.values()];
}
