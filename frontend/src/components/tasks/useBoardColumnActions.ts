import { addCustomColumn, deleteCustomColumn, moveColumnId, renameCustomColumn } from "./boardColumns";
import type { CustomColumn, TaskPreferencesPatch } from "../../api/tasks";

export type BoardKind = "planner" | "deadline";

const FIELD_NAMES = {
  planner: { order: "planner_columns", customColumns: "planner_custom_columns", members: "planner_custom_members" },
  deadline: { order: "deadline_columns", customColumns: "deadline_custom_columns", members: "deadline_custom_members" },
} as const;

/**
 * Add/rename/delete/reorder custom columns — identical mechanics for the planner and the Deadlines
 * board, differing only in which three TaskPreferences fields they write to (D-202). Card movement
 * (within a column, between columns) is handled separately by each board, since the two differ there:
 * a planner move is a real status change, a Deadlines-board move into a system column is a real
 * deadline change, while a move into *either* board's custom column is just a personal placement.
 */
export function useBoardColumnActions(
  kind: BoardKind,
  order: string[],
  customColumns: Record<string, CustomColumn>,
  members: Record<string, string>,
  save: (patch: TaskPreferencesPatch) => void,
) {
  const fields = FIELD_NAMES[kind];

  function addColumn(title: string) {
    const result = addCustomColumn(order, customColumns, title);
    save({ [fields.order]: result.order, [fields.customColumns]: result.customColumns });
  }

  function renameColumn(id: string, title: string) {
    save({ [fields.customColumns]: renameCustomColumn(customColumns, id, title) });
  }

  function deleteColumn(id: string) {
    const result = deleteCustomColumn(order, customColumns, members, id);
    save({ [fields.order]: result.order, [fields.customColumns]: result.customColumns, [fields.members]: result.members });
  }

  function moveColumn(id: string, toIndex: number) {
    save({ [fields.order]: moveColumnId(order, id, toIndex) });
  }

  return { addColumn, renameColumn, deleteColumn, moveColumn };
}
