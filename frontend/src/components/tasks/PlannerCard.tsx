import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { NEXT_STATUSES, TASK_STATUS_LABELS, TRANSITION_LABELS, type CustomColumn, type TaskListItem } from "../../api/tasks";
import { BoardCardBody, BoardCardMenu } from "./BoardCard";

/**
 * One card on the "Мой план" board. Draggable with the pointer (@dnd-kit) and, for keyboard/screen-reader
 * use, offers the same move as explicit controls in its "⋯" menu: up/down buttons reorder within the
 * column, and a "Переместить" select moves it to any other column — same onMove handler the parent uses for a
 * cross-column drop, which decides what a move into a system vs. custom column actually does.
 */
export function PlannerCard({
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
  const statusTargets = NEXT_STATUSES[task.status] ?? [];
  const customTargets = Object.entries(customColumns).filter(([id]) => id !== currentColumnId);
  const targets: [string, string][] = [
    ...statusTargets.map((to): [string, string] => [to, TRANSITION_LABELS[task.status]?.[to] ?? TASK_STATUS_LABELS[to]]),
    ...customTargets.map(([id, column]): [string, string] => [id, column.title]),
  ];

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : undefined }}
      className="board-card"
    >
      <BoardCardBody task={task} dragProps={{ ...attributes, ...listeners }} showStatus={false} />
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
