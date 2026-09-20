import { Link } from "react-router";
import { DEADLINE_GROUP_LABELS, TASK_STATUS_LABELS, type DeadlineGroup, type TaskStatus } from "../../api/tasks";
import { taskPath } from "../../app/navigation";
import { formatDate } from "../../lib/format";

const STATUS_BADGE: Record<TaskStatus, string> = {
  new: "badge-1",
  in_progress: "badge-2",
  awaiting_review: "badge-warning",
  completed: "badge-3",
  deferred: "badge-4",
  cancelled: "badge-danger",
};

export function TaskDeadlineView({ groups }: { groups: DeadlineGroup[] }) {
  const nonEmpty = groups.filter((g) => g.total > 0);
  if (!nonEmpty.length) return <p className="empty">Задач не найдено.</p>;

  return (
    <div className="deadline-view">
      {nonEmpty.map((g) => (
        <section className="deadline-group" key={g.group}>
          <h3>
            {DEADLINE_GROUP_LABELS[g.group]} <span className="muted">{g.total}</span>
          </h3>
          <ul className="task-list">
            {g.items.map((t) => (
              <Link className="task" key={t.id} to={taskPath(t.id)}>
                <span className={`badge ${STATUS_BADGE[t.status]}`}>{TASK_STATUS_LABELS[t.status]}</span>
                <div>
                  <strong>{t.title}</strong>
                  <small>{t.assignees.length ? t.assignees.map((a) => a.full_name).join(", ") : "Без исполнителя"}</small>
                </div>
                <span className="task-date">{t.deadline ? formatDate(t.deadline) : ""}</span>
              </Link>
            ))}
          </ul>
          {g.total > g.items.length && <p className="muted">И ещё {g.total - g.items.length}…</p>}
        </section>
      ))}
    </div>
  );
}
