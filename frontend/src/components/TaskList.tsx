import { useToggleTask } from "../api/queries";
import type { Launch, Task } from "../api/types";
import { formatDate } from "../lib/format";
import { ErrorAlert } from "./QueryState";

export function TaskList({
  rows,
  launches,
}: {
  rows: Task[];
  launches: Launch[];
}) {
  const toggle = useToggleTask();
  return (
    <div className="task-list">
      {toggle.isError && <ErrorAlert error={toggle.error} />}
      {rows.map((t) => (
        <div className={`task ${t.done ? "done" : ""}`} key={t.id}>
          <input
            type="checkbox"
            checked={t.done}
            disabled={toggle.isPending && toggle.variables?.id === t.id}
            aria-label={t.title}
            onChange={() => toggle.mutate({ id: t.id, done: !t.done })}
          />
          <div>
            <strong>{t.title}</strong>
            <small>
              {launches.find((l) => l.id === t.launch_id)?.program} · {t.owner}
            </small>
          </div>
          <span className="task-date">{formatDate(t.deadline)}</span>
        </div>
      ))}
      {!rows.length && <p className="empty">Задач пока нет.</p>}
    </div>
  );
}
