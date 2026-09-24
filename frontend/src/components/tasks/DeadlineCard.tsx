import { Link } from "react-router";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, type CustomColumn, type TaskListItem } from "../../api/tasks";
import { taskPath } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import { DEADLINE_SYSTEM_COLUMNS } from "./deadlineBoard";
import { STATUS_BADGE } from "./taskDisplay";


/**
 * One card on the "Сроки" board. Draggable with the pointer (@dnd-kit) and, for keyboard/screen-reader
 * use, offers the same move as explicit controls: up/down buttons reorder within the column, and a
 * "Переместить" select moves it to any other column — every system column is always offered (any
 * deadline is a valid deadline, unlike the planner's status transitions), plus every custom column.
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
  const systemTargets = DEADLINE_SYSTEM_COLUMNS.filter((c) => c.key !== currentColumnId);
  const customTargets = Object.entries(customColumns).filter(([id]) => id !== currentColumnId);

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
        <span className={STATUS_BADGE[task.status]}>{TASK_STATUS_LABELS[task.status]}</span>
        {" · "}
        {TASK_PRIORITY_LABELS[task.priority]}
        {task.deadline ? ` · ${formatDate(task.deadline)}` : " · Без срока"}
      </div>
      {task.assignees.length > 0 && (
        <div className="planner-card-assignees muted">{task.assignees.map((a) => a.full_name).join(", ")}</div>
      )}
      {task.university && <div className="planner-card-assignees muted">{task.university.name}</div>}
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
        <label className="planner-card-move">
          {`Переместить «${task.title}»`}
          <select value="" onChange={(e) => e.target.value && onMove(e.target.value)}>
            <option value="" disabled>
              Выбрать колонку
            </option>
            {systemTargets.map((c) => (
              <option value={c.key} key={c.key}>
                {c.label}
              </option>
            ))}
            {customTargets.map(([id, column]) => (
              <option value={id} key={id}>
                {column.title}
              </option>
            ))}
          </select>
        </label>
      </div>
    </li>
  );
}
