import { useState } from "react";
import { Link } from "react-router";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import {
  NEEDS_COMMENT,
  NEXT_STATUSES,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
  TRANSITION_LABELS,
  useChangeTaskStatus,
  type TaskListItem,
  type TaskStatus,
} from "../../api/tasks";
import { errorText } from "../../api/client";
import { taskPath } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import { StatusCommentModal } from "./StatusCommentModal";

/**
 * One card on the "Мой план" board. Draggable with the pointer (@dnd-kit) and, for keyboard/screen-reader
 * use, offers the same move as explicit controls: up/down buttons reorder within the column, and a
 * "Переместить" select changes status exactly like a cross-column drop would — same handler either way.
 */
export function PlannerCard({
  task,
  index,
  columnSize,
  onMoveWithinColumn,
}: {
  task: TaskListItem;
  index: number;
  columnSize: number;
  onMoveWithinColumn: (direction: -1 | 1) => void;
}) {
  const [pendingComment, setPendingComment] = useState<TaskStatus | null>(null);
  const change = useChangeTaskStatus(task.id);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id });
  const options = NEXT_STATUSES[task.status] ?? [];

  function go(to: TaskStatus, comment = "") {
    change.mutate({ to_status: to, comment, version: task.version });
  }

  function move(to: TaskStatus) {
    const key = `${task.status}:${to}`;
    if (NEEDS_COMMENT.has(key)) setPendingComment(to);
    else go(to);
  }

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
        {options.length > 0 && (
          <label className="planner-card-move">
            {`Переместить «${task.title}»`}
            <select
              value=""
              disabled={change.isPending}
              onChange={(e) => e.target.value && move(e.target.value as TaskStatus)}
            >
              <option value="" disabled>
                Выбрать статус
              </option>
              {options.map((to) => (
                <option value={to} key={to}>
                  {TRANSITION_LABELS[task.status]?.[to] ?? TASK_STATUS_LABELS[to]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {change.isError && (
        <p className="danger" role="alert">
          {errorText(change.error)}
        </p>
      )}
      {pendingComment && (
        <StatusCommentModal
          pending={change.isPending}
          error={change.error}
          onCancel={() => setPendingComment(null)}
          onSubmit={(comment) => {
            go(pendingComment, comment);
            setPendingComment(null);
          }}
        />
      )}
    </li>
  );
}
