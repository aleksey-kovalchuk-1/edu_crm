import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { CustomColumn, TaskListItem } from "../../api/tasks";
import { BoardCardBody, BoardCardMenu } from "./BoardCard";
import { DEADLINE_SYSTEM_COLUMNS } from "./deadlineBoard";

/**
 * One card on the "Сроки" board. Draggable with the pointer (@dnd-kit) and, for keyboard/screen-reader
 * use, offers the same move as explicit controls in its "⋯" menu: up/down buttons reorder within the
 * column, and a "Переместить" select moves it to any other column — every system column is always
 * offered (any deadline is a valid deadline, unlike the planner's status transitions), plus every
 * custom column.
 */
export function DeadlineCard({
  task,
  index,
  columnSize,
  currentColumnId,
  customColumns,
  onMoveWithinColumn,
  onMove,
}: {
  task: TaskListItem;
  index: number;
  columnSize: number;
  currentColumnId: string;
  customColumns: Record<string, CustomColumn>;
  onMoveWithinColumn: (direction: -1 | 1) => void;
  onMove: (toColumnId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id });
  const targets: [string, string][] = [
    ...DEADLINE_SYSTEM_COLUMNS.filter((c) => c.key !== currentColumnId).map((c): [string, string] => [c.key, c.label]),
    ...Object.entries(customColumns)
      .filter(([id]) => id !== currentColumnId)
      .map(([id, column]): [string, string] => [id, column.title]),
  ];

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : undefined }}
      className="board-card"
    >
      <BoardCardBody task={task} dragProps={{ ...attributes, ...listeners }} showStatus />
      <BoardCardMenu
        task={task}
        index={index}
        columnSize={columnSize}
        onMoveWithinColumn={onMoveWithinColumn}
        onMove={onMove}
        targets={targets}
      />
    </li>
  );
}
