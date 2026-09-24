import type { ReactNode } from "react";
import { Link } from "react-router";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Flame, GitBranch, ListChecks, MessageSquare } from "lucide-react";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, type TaskListItem, type TaskPriority } from "../../api/tasks";
import { taskPath } from "../../app/navigation";
import { formatDate, formatRelativeTime } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { PersonAvatars } from "./PersonAvatars";
import { STATUS_BADGE, deadlineInfo } from "./taskDisplay";

const PRIORITY_ICON: Record<TaskPriority, ReactNode> = {
  urgent: <Flame size={14} aria-hidden="true" />,
  high: <ArrowUp size={14} aria-hidden="true" />,
  normal: null,
  low: <ArrowDown size={14} aria-hidden="true" />,
};

/** Column key → header label and the `sort` field its header toggles (null: not sortable). */
const COLUMNS: Record<string, { label: string; sort: string | null }> = {
  status: { label: "Статус", sort: "status" },
  deadline: { label: "Срок", sort: "deadline" },
  assignees: { label: "Исполнители", sort: null },
  priority: { label: "Приоритет", sort: "priority" },
  creator: { label: "Постановщик", sort: null },
  updated_at: { label: "Изменена", sort: "updated_at" },
  university: { label: "Учебное заведение", sort: null },
  created_at: { label: "Создана", sort: "created_at" },
};
const COLUMN_ORDER = Object.keys(COLUMNS);

function SortHeader({
  label,
  field,
  sort,
  onSort,
}: {
  label: string;
  field: string | null;
  sort: string;
  onSort: (field: string) => void;
}) {
  if (!field) return <th scope="col">{label}</th>;
  const active = sort.replace(/^-/, "") === field;
  const desc = sort.startsWith("-");
  return (
    <th scope="col" aria-sort={active ? (desc ? "descending" : "ascending") : "none"}>
      <button type="button" className={active ? "th-sort active" : "th-sort"} onClick={() => onSort(field)}>
        {label}
        {active && (desc ? <ArrowDown size={12} aria-hidden="true" /> : <ArrowUp size={12} aria-hidden="true" />)}
      </button>
    </th>
  );
}

/** Institution · interaction, then checklist / subtask / comment counts — the context a row needs at a glance. */
function RowContext({ task, showUniversity }: { task: TaskListItem; showUniversity: boolean }) {
  const place = [showUniversity ? task.university?.name : null, task.interaction?.program].filter(Boolean).join(" · ");
  const { checklist_progress: checklist, subtasks, comment_count: comments } = task;
  if (!place && !checklist.total && !subtasks.total && !comments) return null;
  return (
    <div className="task-row-context">
      {place && <span className="task-row-place">{place}</span>}
      {checklist.total > 0 && (
        <span className="task-row-count" title="Чек-лист выполнен" aria-label={`Чек-лист: ${checklist.completed} из ${checklist.total}`}>
          <ListChecks size={13} aria-hidden="true" />
          {checklist.completed}/{checklist.total}
        </span>
      )}
      {subtasks.total > 0 && (
        <span className="task-row-count" title="Подзадачи завершены" aria-label={`Подзадачи: ${subtasks.completed} из ${subtasks.total}`}>
          <GitBranch size={13} aria-hidden="true" />
          {subtasks.completed}/{subtasks.total}
        </span>
      )}
      {comments > 0 && (
        <span className="task-row-count" title="Комментарии" aria-label={`Комментариев: ${comments}`}>
          <MessageSquare size={13} aria-hidden="true" />
          {comments}
        </span>
      )}
    </div>
  );
}

export function TaskListView({
  items,
  total,
  limit,
  offset,
  columns,
  sort,
  selected,
  quickAdd,
  onSort,
  onToggle,
  onToggleAll,
  onPage,
}: {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
  columns: string[];
  sort: string;
  selected: Set<number>;
  /** Rendered above the rows (the quick-add line). */
  quickAdd?: ReactNode;
  onSort: (field: string) => void;
  onToggle: (id: number) => void;
  onToggleAll: () => void;
  onPage: (offset: number) => void;
}) {
  const from = total ? offset + 1 : 0;
  const to = offset + items.length;
  const allSelected = items.length > 0 && items.every((t) => selected.has(t.id));
  const visible = COLUMN_ORDER.filter((key) => columns.includes(key));
  const now = useNow();
  const today = new Date(now);

  function cell(t: TaskListItem, key: string): ReactNode {
    switch (key) {
      case "status":
        return <span className={STATUS_BADGE[t.status]}>{TASK_STATUS_LABELS[t.status]}</span>;
      case "deadline": {
        const d = deadlineInfo(t.deadline, t.status, today);
        return (
          <span className={`deadline-pill tone-${d.tone}`} title={d.title}>
            {d.label}
          </span>
        );
      }
      case "assignees":
        return <PersonAvatars people={t.assignees} />;
      case "priority":
        return (
          <span className={`priority-mark priority-${t.priority}`}>
            {PRIORITY_ICON[t.priority]}
            {TASK_PRIORITY_LABELS[t.priority]}
          </span>
        );
      case "creator":
        return <PersonAvatars people={t.creator ? [t.creator] : []} />;
      case "updated_at":
        return <span className="muted">{formatRelativeTime(t.updated_at, now)}</span>;
      case "university":
        return t.university?.name ?? <span className="muted">—</span>;
      case "created_at":
        return formatDate(t.created_at);
      default:
        return null;
    }
  }

  return (
    <>
      <div className="table-wrap task-table" aria-busy={false}>
        {quickAdd}
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col" className="cell-check">
                <input
                  type="checkbox"
                  aria-label="Выбрать все задачи на странице"
                  checked={allSelected}
                  onChange={onToggleAll}
                />
              </th>
              <SortHeader label="Название" field="title" sort={sort} onSort={onSort} />
              {visible.map((key) => (
                <SortHeader key={key} label={COLUMNS[key].label} field={COLUMNS[key].sort} sort={sort} onSort={onSort} />
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} className={selected.has(t.id) ? "selected" : undefined}>
                <td className="cell-check">
                  <input
                    type="checkbox"
                    aria-label={`Выбрать «${t.title}»`}
                    checked={selected.has(t.id)}
                    onChange={() => onToggle(t.id)}
                  />
                </td>
                <td className="task-title-cell">
                  <Link className="cell-title" to={taskPath(t.id)}>
                    {t.title}
                  </Link>
                  <RowContext task={t} showUniversity={!columns.includes("university")} />
                </td>
                {visible.map((key) => (
                  <td key={key}>{cell(t, key)}</td>
                ))}
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
      ) : null}
    </>
  );
}
