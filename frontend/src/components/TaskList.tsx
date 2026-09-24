import { Link } from "react-router";
import { TASK_STATUS_LABELS, type TaskListItem } from "../api/tasks";
import { taskPath } from "../app/navigation";
import { formatDate } from "../lib/format";
import { STATUS_BADGE } from "./tasks/taskDisplay";


/**
 * Read-only preview list (used on the overview dashboard). Changing status,
 * assignees or anything else happens on the task's own page — this list only links there.
 */
export function TaskList({ items }: { items: TaskListItem[] }) {
  return (
    <div className="task-list">
      {items.map((t) => (
        <Link className="task" key={t.id} to={taskPath(t.id)}>
          <span className={STATUS_BADGE[t.status]}>{TASK_STATUS_LABELS[t.status]}</span>
          <div>
            <strong>{t.title}</strong>
            <small>
              {t.assignees.length ? t.assignees.map((a) => a.full_name).join(", ") : "Без исполнителя"}
            </small>
          </div>
          <span className="task-date">{t.deadline ? formatDate(t.deadline) : "Без срока"}</span>
        </Link>
      ))}
      {!items.length && <p className="empty">Задач пока нет.</p>}
    </div>
  );
}
