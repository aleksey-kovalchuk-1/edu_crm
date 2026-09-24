import { useState, type FormEvent } from "react";
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { errorText } from "../../api/client";
import {
  useAddChecklistItem,
  useDeleteChecklistItem,
  useReorderChecklist,
  useUpdateChecklistItem,
  type ChecklistItem,
} from "../../api/tasks";
import { formatDate } from "../../lib/format";

/**
 * Move-up/move-down buttons rather than pointer drag-and-drop: fully keyboard-operable without a
 * new dependency (docs/design/tasks.md — dnd-kit is reserved for the Planner board in a later slice,
 * where drag is the primary interaction; here a button pair covers the same reordering need).
 */
export function TaskChecklist({ taskId, items }: { taskId: number; items: ChecklistItem[] }) {
  const [title, setTitle] = useState("");
  const add = useAddChecklistItem(taskId);
  const update = useUpdateChecklistItem(taskId);
  const remove = useDeleteChecklistItem(taskId);
  const reorder = useReorderChecklist(taskId);
  const sorted = [...items].sort((a, b) => a.position - b.position);
  const done = sorted.filter((i) => i.is_done).length;

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim()) return;
    add.mutate({ title: title.trim() }, { onSuccess: () => setTitle("") });
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= sorted.length) return;
    const ids = sorted.map((i) => i.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate(ids);
  }

  return (
    <div className="task-checklist">
      <div className="section-head">
        <h3>Чек-лист</h3>
        {sorted.length > 0 && (
          <span className="muted">
            {done} из {sorted.length}
          </span>
        )}
      </div>
      <ul className="checklist-items">
        {sorted.map((item, index) => (
          <li key={item.id} className={item.is_done ? "done" : undefined}>
            <label>
              <input
                type="checkbox"
                checked={item.is_done}
                disabled={update.isPending}
                onChange={(e) => update.mutate({ id: item.id, is_done: e.target.checked })}
              />
              <span>{item.title}</span>
            </label>
            {(item.assignee || item.deadline) && (
              <small className="muted">
                {item.assignee?.full_name}
                {item.assignee && item.deadline ? " · " : ""}
                {item.deadline && formatDate(item.deadline)}
              </small>
            )}
            <div className="checklist-item-actions">
              <button
                type="button"
                className="icon-button"
                aria-label={`Переместить «${item.title}» выше`}
                disabled={index === 0 || reorder.isPending}
                onClick={() => move(index, -1)}
              >
                <ArrowUp size={14} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`Переместить «${item.title}» ниже`}
                disabled={index === sorted.length - 1 || reorder.isPending}
                onClick={() => move(index, 1)}
              >
                <ArrowDown size={14} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`Удалить «${item.title}»`}
                disabled={remove.isPending}
                onClick={() => remove.mutate(item.id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </li>
        ))}
        {!sorted.length && <p className="empty">Пунктов пока нет.</p>}
      </ul>
      <form onSubmit={submit} className="checklist-add">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Добавить пункт"
          maxLength={200}
          aria-label="Название пункта чек-листа"
        />
        <button type="submit" className="secondary" disabled={add.isPending || !title.trim()}>
          Добавить
        </button>
      </form>
      {(add.isError || update.isError || remove.isError || reorder.isError) && (
        <p className="danger" role="alert">
          {errorText(add.error ?? update.error ?? remove.error ?? reorder.error)}
        </p>
      )}
    </div>
  );
}
