import { TASK_STATUS_LABELS, useActivity, type TaskActivityEvent, type TaskStatus } from "../../api/tasks";
import { formatDateTime } from "../../lib/format";

const EVENT_LABELS: Record<string, string> = {
  created: "Задача создана",
  updated: "Изменены поля задачи",
  status_change: "Смена статуса",
  reassignment: "Изменён состав участников",
  checklist_item_added: "Добавлен пункт чек-листа",
  checklist_item_updated: "Изменён пункт чек-листа",
  checklist_item_completed: "Отмечен пункт чек-листа",
  checklist_item_removed: "Удалён пункт чек-листа",
  comment_added: "Добавлен комментарий",
};

const statusLabel = (value: string | null) => (value && value in TASK_STATUS_LABELS ? TASK_STATUS_LABELS[value as TaskStatus] : value);

function ActivityRow({ event }: { event: TaskActivityEvent }) {
  const label = EVENT_LABELS[event.event_type] ?? event.event_type;
  return (
    <li className="activity-item">
      <div>
        <strong>{label}</strong>
        {event.event_type === "status_change" && (
          <span className="muted">
            {" "}
            «{statusLabel(event.from_value)}» → «{statusLabel(event.to_value)}»
          </span>
        )}
        {event.comment && <p className="muted">{event.comment}</p>}
      </div>
      <div className="activity-meta">
        <span>{event.actor?.full_name ?? "Система"}</span>
        <time>{formatDateTime(event.created_at)}</time>
      </div>
    </li>
  );
}

export function TaskActivity({ taskId }: { taskId: number }) {
  const activity = useActivity(taskId);
  return (
    <div className="task-activity">
      <h3>Лента событий</h3>
      <ul className="activity-list">
        {activity.data?.map((e) => (
          <ActivityRow event={e} key={e.id} />
        ))}
        {activity.data && !activity.data.length && <p className="empty">Событий пока нет.</p>}
      </ul>
    </div>
  );
}
