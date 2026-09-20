import { Link } from "react-router";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { NEXT_STATUSES, TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, TRANSITION_LABELS, type CustomColumn, type TaskListItem } from "../../api/tasks";
import { taskPath } from "../../app/navigation";
import { formatDate } from "../../lib/format";

/**
 * One card on the "Мой план" board. Draggable with the pointer (@dnd-kit) and, for keyboard/screen-reader
 * use, offers the same move as explicit controls: up/down buttons reorder within the column, and a
 * "Переместить" select moves it to any other column — same onMove handler the parent uses for a
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
  const hasTargets = statusTargets.length > 0 || customTargets.length > 0;

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : undefined }}
      className="planner-card"
    >
      <div className="planner-card-head">
        <button
          type="button"
          className="icon-button planner-card-handle"
          aria-label={`Перетащить «${task.title}»`}
          {...attributes}
          {...listeners}
        >
          <GripVertical size={14} />
        </button>
        <Link className="cell-title" to={taskPath(task.id)}>
          {task.title}
        </Link>
      </div>
      <div className="planner-card-meta muted">
        {TASK_PRIORITY_LABELS[task.priority]}
        {task.deadline ? ` · ${formatDate(task.deadline)}` : ""}
      </div>
      {task.assignees.length > 0 && (
        <div className="planner-card-assignees muted">{task.assignees.map((a) => a.full_name).join(", ")}</div>
      )}
      <div className="planner-card-controls">
        <span className="planner-card-order">
          <button
            type="button"
            className="icon-button"
            aria-label={`Переместить «${task.title}» выше в колонке`}
            disabled={index === 0}
            onClick={() => onMoveWithinColumn(-1)}
          >
            <ArrowUp size={13} />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label={`Переместить «${task.title}» ниже в колонке`}
            disabled={index === columnSize - 1}
            onClick={() => onMoveWithinColumn(1)}
          >
            <ArrowDown size={13} />
          </button>
        </span>
        {hasTargets && (
          <label className="planner-card-move">
            {`Переместить «${task.title}»`}
            <select value="" onChange={(e) => e.target.value && onMove(e.target.value)}>
              <option value="" disabled>
                Выбрать колонку
              </option>
              {statusTargets.map((to) => (
                <option value={to} key={to}>
                  {TRANSITION_LABELS[task.status]?.[to] ?? TASK_STATUS_LABELS[to]}
                </option>
              ))}
              {customTargets.map(([id, column]) => (
                <option value={id} key={id}>
                  {column.title}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
    </li>
  );
}
