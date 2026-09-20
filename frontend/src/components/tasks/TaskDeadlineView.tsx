import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { DEADLINE_GROUP_LABELS, TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, type DeadlineGroup, type TaskStatus } from "../../api/tasks";
import { taskPath } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import { deadlineGroupListLink } from "./taskFilterState";

const STATUS_BADGE: Record<TaskStatus, string> = {
  new: "badge-1",
  in_progress: "badge-2",
  awaiting_review: "badge-warning",
  completed: "badge-3",
  deferred: "badge-4",
  cancelled: "badge-danger",
};

/**
 * Grouped by deadline bucket (docs/design/tasks.md, D-172); each bucket is a keyboard-operable
 * <details> disclosure (collapsible, open by default — same pattern as the column pickers) rather than
 * a fixed always-expanded stack, and a truncated group's "и ещё N…" is a real link into the List view
 * pre-filtered to that exact bucket instead of a dead end (D-196).
 */
export function TaskDeadlineView({ groups, params }: { groups: DeadlineGroup[]; params: URLSearchParams }) {
  const nonEmpty = groups.filter((g) => g.total > 0);
  if (!nonEmpty.length) return <p className="empty">Задач не найдено.</p>;

  return (
    <div className="deadline-view">
      {nonEmpty.map((g) => (
        <details className="deadline-group" key={g.group} open>
          <summary>
            <ChevronRight className="deadline-group-chevron" size={15} aria-hidden />
            <h3>
              {DEADLINE_GROUP_LABELS[g.group]} <span className="muted">{g.total}</span>
            </h3>
          </summary>
          <ul className="task-list">
            {g.items.map((t) => (
              <Link className="task" key={t.id} to={taskPath(t.id)}>
                <span className={`badge ${STATUS_BADGE[t.status]}`}>{TASK_STATUS_LABELS[t.status]}</span>
                <div>
                  <strong>{t.title}</strong>
                  <small>{t.assignees.length ? t.assignees.map((a) => a.full_name).join(", ") : "Без исполнителя"}</small>
                </div>
                <small className="muted deadline-priority">{TASK_PRIORITY_LABELS[t.priority]}</small>
                <span className="task-date">{t.deadline ? formatDate(t.deadline) : ""}</span>
              </Link>
            ))}
          </ul>
          {g.total > g.items.length && (
            <Link className="text-button deadline-more" to={deadlineGroupListLink(params, g.group)}>
              И ещё {g.total - g.items.length} — показать в списке задач
            </Link>
          )}
        </details>
      ))}
    </div>
  );
}
