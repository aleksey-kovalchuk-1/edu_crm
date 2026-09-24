import { Link } from "react-router";
import { ArrowDown, ArrowUp, Flame, GripVertical, ListChecks, MessageSquare, MoreHorizontal } from "lucide-react";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, type TaskListItem } from "../../api/tasks";
import { taskPath } from "../../app/navigation";
import { useNow } from "../../lib/useNow";
import { PersonAvatars } from "./PersonAvatars";
import { STATUS_BADGE, deadlineInfo } from "./taskDisplay";

type DragProps = Record<string, unknown>;

/**
 * The shared body of a card on «Сроки» and «Мой план»: drag handle and title, the deadline as a
 * coloured pill (plus a priority mark only when it is high or urgent), institution · interaction,
 * then assignees and checklist/comment counts. `showStatus` is off on «Мой план», where the column
 * already is the status.
 */
export function BoardCardBody({
  task,
  dragProps,
  showStatus,
}: {
  task: TaskListItem;
  dragProps: DragProps;
  showStatus: boolean;
}) {
  const now = useNow();
  const deadline = deadlineInfo(task.deadline, task.status, new Date(now));
  const place = [task.university?.name, task.interaction?.program].filter(Boolean).join(" · ");
  const urgent = task.priority === "urgent" || task.priority === "high";
  const { checklist_progress: checklist, comment_count: comments } = task;

  return (
    <>
      <div className="board-card-head">
        <button type="button" className="icon-button board-card-handle" aria-label={`Перетащить «${task.title}»`} {...dragProps}>
          <GripVertical size={14} />
        </button>
        <Link className="board-card-title" to={taskPath(task.id)}>
          {task.title}
        </Link>
      </div>
      <div className="board-card-tags">
        {showStatus && <span className={STATUS_BADGE[task.status]}>{TASK_STATUS_LABELS[task.status]}</span>}
        <span className={`deadline-pill tone-${deadline.tone}`} title={deadline.title}>
          {deadline.label}
        </span>
        {urgent && (
          <span className={`priority-mark priority-${task.priority}`}>
            {task.priority === "urgent" ? <Flame size={13} aria-hidden="true" /> : <ArrowUp size={13} aria-hidden="true" />}
            {TASK_PRIORITY_LABELS[task.priority]}
          </span>
        )}
      </div>
      {place && <div className="board-card-place">{place}</div>}
      <div className="board-card-foot">
        <PersonAvatars people={task.assignees} />
        <span className="board-card-counts">
          {checklist.total > 0 && (
            <span className="task-row-count" aria-label={`Чек-лист: ${checklist.completed} из ${checklist.total}`}>
              <ListChecks size={13} aria-hidden="true" />
              {checklist.completed}/{checklist.total}
            </span>
          )}
          {comments > 0 && (
            <span className="task-row-count" aria-label={`Комментариев: ${comments}`}>
              <MessageSquare size={13} aria-hidden="true" />
              {comments}
            </span>
          )}
        </span>
      </div>
    </>
  );
}

/**
 * The keyboard / screen-reader alternative to dragging, tucked behind a "⋯" disclosure so it no
 * longer fills every card: up/down within the column, and a «Переместить» select for any other column.
 */
export function BoardCardMenu({
  task,
  index,
  columnSize,
  onMoveWithinColumn,
  onMove,
  targets,
}: {
  task: TaskListItem;
  index: number;
  columnSize: number;
  onMoveWithinColumn: (direction: -1 | 1) => void;
  onMove: (toColumnId: string) => void;
  /** Other columns this card may move to, as [id, label]. */
  targets: [string, string][];
}) {
  return (
    <details className="board-card-menu">
      <summary aria-label={`Действия с «${task.title}»`}>
        <MoreHorizontal size={16} aria-hidden="true" />
      </summary>
      <div className="board-card-menu-panel">
        <span className="board-card-order">
          <button
            type="button"
            className="icon-button"
            aria-label={`Переместить «${task.title}» выше в колонке`}
            disabled={index === 0}
            onClick={() => onMoveWithinColumn(-1)}
          >
            <ArrowUp size={14} />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label={`Переместить «${task.title}» ниже в колонке`}
            disabled={index === columnSize - 1}
            onClick={() => onMoveWithinColumn(1)}
          >
            <ArrowDown size={14} />
          </button>
        </span>
        {targets.length > 0 && (
          <select
            className="board-card-move"
            value=""
            aria-label={`Переместить «${task.title}»`}
            onChange={(e) => e.target.value && onMove(e.target.value)}
          >
            <option value="" disabled>
              Переместить в…
            </option>
            {targets.map(([id, label]) => (
              <option value={id} key={id}>
                {label}
              </option>
            ))}
          </select>
        )}
      </div>
    </details>
  );
}
