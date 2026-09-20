import { useState } from "react";
import { useUniversities } from "../../api/catalogs";
import {
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
  type DeadlinePreset,
  type SavedFilterSet,
  type TaskPriority,
  type TaskStatus,
} from "../../api/tasks";
import { Modal } from "../Modal";

const DEADLINE_PRESETS: { value: DeadlinePreset; label: string }[] = [
  { value: "overdue", label: "Просрочено" },
  { value: "today", label: "Срок сегодня" },
  { value: "this_week", label: "На этой неделе" },
  { value: "next_week", label: "На следующей неделе" },
  { value: "no_deadline", label: "Без срока" },
];

const ALL_STATUSES = Object.keys(TASK_STATUS_LABELS) as TaskStatus[];
const ALL_PRIORITIES = Object.keys(TASK_PRIORITY_LABELS) as TaskPriority[];

const EMPTY_DRAFT: SavedFilterSet = {
  status: [],
  priority: [],
  university_id: undefined,
  deadline_preset: undefined,
  active: undefined,
  has_checklist: undefined,
};

/**
 * Filters draft editor, opened from the "Фильтры" toolbar button. Editing here never touches the
 * applied filters, the URL or saved preferences until "Сохранить" is pressed — Cancel (the close icon,
 * Escape, and the backdrop, all wired through Modal's native <dialog>) simply discards the draft.
 */
export function TaskFilterDialog({
  initial,
  scopeLabel,
  onCancel,
  onSave,
}: {
  initial: SavedFilterSet;
  scopeLabel: string;
  onCancel: () => void;
  onSave: (filters: SavedFilterSet) => void;
}) {
  const [draft, setDraft] = useState<SavedFilterSet>(initial);
  const universities = useUniversities();
  const status = draft.status ?? [];
  const priority = draft.priority ?? [];

  function toggle(key: "status" | "priority", value: string, current: string[]) {
    setDraft((prev) => ({ ...prev, [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] }));
  }

  return (
    <Modal title="Фильтры задач" close={onCancel} wide>
      <p className="modal-subtitle muted">Область: {scopeLabel}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(draft);
        }}
      >
        <div className="filter-dialog-presets">
          {DEADLINE_PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              className={draft.deadline_preset === p.value ? "secondary selected" : "secondary"}
              onClick={() => setDraft((prev) => ({ ...prev, deadline_preset: prev.deadline_preset === p.value ? undefined : p.value }))}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="filter-dialog-fields">
          <fieldset>
            <legend>Статус</legend>
            {ALL_STATUSES.map((s) => (
              <label key={s} className="toggle">
                <input type="checkbox" checked={status.includes(s)} onChange={() => toggle("status", s, status)} />
                {TASK_STATUS_LABELS[s]}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Приоритет</legend>
            {ALL_PRIORITIES.map((p) => (
              <label key={p} className="toggle">
                <input type="checkbox" checked={priority.includes(p)} onChange={() => toggle("priority", p, priority)} />
                {TASK_PRIORITY_LABELS[p]}
              </label>
            ))}
          </fieldset>
          <label className="inline-select">
            Вуз
            <select
              value={draft.university_id ?? ""}
              onChange={(e) => setDraft((prev) => ({ ...prev, university_id: e.target.value ? Number(e.target.value) : undefined }))}
            >
              <option value="">Любой</option>
              {universities.data?.map((u) => (
                <option value={u.id} key={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </label>
          <label className="inline-select">
            Активность
            <select
              value={draft.active === undefined ? "" : String(draft.active)}
              onChange={(e) => setDraft((prev) => ({ ...prev, active: e.target.value ? e.target.value === "true" : undefined }))}
            >
              <option value="">Все</option>
              <option value="true">Только активные</option>
              <option value="false">Только завершённые</option>
            </select>
          </label>
          <label className="inline-select">
            Чек-лист
            <select
              value={draft.has_checklist === undefined ? "" : String(draft.has_checklist)}
              onChange={(e) => setDraft((prev) => ({ ...prev, has_checklist: e.target.value ? e.target.value === "true" : undefined }))}
            >
              <option value="">Не важно</option>
              <option value="true">С чек-листом</option>
              <option value="false">Без чек-листа</option>
            </select>
          </label>
        </div>
        <div className="modal-actions filter-dialog-actions">
          <button type="button" className="text-button" onClick={() => setDraft(EMPTY_DRAFT)}>
            Сбросить
          </button>
          <div className="filter-dialog-actions-right">
            <button type="button" className="secondary" onClick={onCancel}>
              Отмена
            </button>
            <button type="submit" className="primary">
              Сохранить
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
