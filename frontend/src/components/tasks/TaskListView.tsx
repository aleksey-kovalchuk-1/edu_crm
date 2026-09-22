import { Link } from "react-router";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, type TaskListItem, type TaskStatus } from "../../api/tasks";
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

export function TaskListView({
  items,
  total,
  limit,
  offset,
  columns,
  selected,
  onToggle,
  onToggleAll,
  onPage,
}: {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
  columns: string[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: () => void;
  onPage: (offset: number) => void;
}) {
  const from = total ? offset + 1 : 0;
  const to = offset + items.length;
  const allSelected = items.length > 0 && items.every((t) => selected.has(t.id));

  return (
    <>
      <div className="table-wrap" aria-busy={false}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">
                <input
                  type="checkbox"
                  aria-label="Выбрать все задачи на странице"
                  checked={allSelected}
                  onChange={onToggleAll}
                />
              </th>
              <th scope="col">Название</th>
              {columns.includes("status") && <th scope="col">Статус</th>}
              {columns.includes("priority") && <th scope="col">Приоритет</th>}
              {columns.includes("deadline") && <th scope="col">Срок</th>}
              {columns.includes("creator") && <th scope="col">Создатель</th>}
              {columns.includes("assignees") && <th scope="col">Исполнители</th>}
              {columns.includes("university") && <th scope="col">Учебное заведение</th>}
              {columns.includes("created_at") && <th scope="col">Создана</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Выбрать «${t.title}»`}
                    checked={selected.has(t.id)}
                    onChange={() => onToggle(t.id)}
                  />
                </td>
                <td>
                  <Link className="cell-title" to={taskPath(t.id)}>
                    {t.title}
                  </Link>
                </td>
                {columns.includes("status") && (
                  <td>
                    <span className={`badge ${STATUS_BADGE[t.status]}`}>{TASK_STATUS_LABELS[t.status]}</span>
                  </td>
                )}
                {columns.includes("priority") && <td>{TASK_PRIORITY_LABELS[t.priority]}</td>}
                {columns.includes("deadline") && (
                  <td>{t.deadline ? formatDate(t.deadline) : <span className="muted">Без срока</span>}</td>
                )}
                {columns.includes("creator") && <td>{t.creator?.full_name ?? <span className="muted">—</span>}</td>}
                {columns.includes("assignees") && (
                  <td>{t.assignees.length ? t.assignees.map((a) => a.full_name).join(", ") : <span className="muted">—</span>}</td>
                )}
                {columns.includes("university") && <td>{t.university?.name ?? <span className="muted">—</span>}</td>}
                {columns.includes("created_at") && <td>{formatDate(t.created_at)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <p className="empty">Задач не найдено.</p>}
      </div>
      {total > limit || offset > 0 ? (
        <nav className="pagination" aria-label="Страницы задач">
          <span className="muted">
            {from}–{to} из {total}
          </span>
          <button type="button" className="secondary" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - limit))}>
            <ChevronLeft size={16} /> Назад
          </button>
          <button type="button" className="secondary" disabled={to >= total} onClick={() => onPage(offset + limit)}>
            Вперёд <ChevronRight size={16} />
          </button>
        </nav>
      ) : (
        <p className="table-total muted">Всего: {total}</p>
      )}
    </>
  );
}
