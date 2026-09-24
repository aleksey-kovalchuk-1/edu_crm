import { useState } from "react";
import { useUniversities } from "../../api/catalogs";
import {
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
  useAssignableUsers,
  type DeadlinePreset,
  type SavedFilterSet,
  type TaskPriority,
  type TaskStatus,
} from "../../api/tasks";
import { Modal } from "../Modal";

export const DEADLINE_PRESET_LABELS: Record<DeadlinePreset, string> = {
  overdue: "Просрочено",
  today: "Сегодня",
  this_week: "На этой неделе",
  next_week: "На следующей неделе",
  later: "Позже",
  no_deadline: "Без срока",
};

const ALL_STATUSES = Object.keys(TASK_STATUS_LABELS) as TaskStatus[];
const ALL_PRIORITIES = Object.keys(TASK_PRIORITY_LABELS) as TaskPriority[];

const EMPTY_DRAFT: SavedFilterSet = {
  status: [],
  priority: [],
  university_id: undefined,
  assignee_id: undefined,
  creator_id: undefined,
  deadline_preset: undefined,
  active: undefined,
  has_checklist: undefined,
};

type IdField = "university_id" | "assignee_id" | "creator_id";

/**
 * Filters draft editor, opened from the "Фильтры" button in the search bar. Only the dimensions
 * people actually filter a CRM task list by: status, priority, who does it, who set it, which
 * institution and when it is due. Editing never touches the applied filters, the URL or saved
 * preferences until "Сохранить" — Cancel (the close icon, Escape, the backdrop) discards the draft.
 * `active`/`has_checklist` from older saved presets are carried through untouched (and removable as
 * chips), just no longer offered here.
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
  const people = useAssignableUsers();
  const status = draft.status ?? [];
  const priority = draft.priority ?? [];

  function toggle(key: "status" | "priority", value: string, current: string[]) {
    setDraft((prev) => ({ ...prev, [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] }));
  }

  function idSelect(field: IdField, label: string, options: { id: number; name: string }[] | undefined) {
    return (
      <label className="filter-field">
        {label}
        <select
          value={draft[field] ?? ""}
          onChange={(e) => setDraft((prev) => ({ ...prev, [field]: e.target.value ? Number(e.target.value) : undefined }))}
        >
          <option value="">Любой</option>
          {options?.map((o) => (
            <option value={o.id} key={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      </label>
    );
  }

  const personOptions = people.data?.map((p) => ({ id: p.id, name: p.full_name }));

  return (
    <Modal title="Фильтры задач" close={onCancel}>
      <p className="modal-subtitle muted">Область: {scopeLabel}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(draft);
        }}
      >
        <fieldset className="filter-fieldset">
          <legend>Статус</legend>
          <div className="filter-toggle-row">
            {ALL_STATUSES.map((s) => (
              <label key={s} className="filter-pill">
                <input type="checkbox" checked={status.includes(s)} onChange={() => toggle("status", s, status)} />
                {TASK_STATUS_LABELS[s]}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="filter-fieldset">
          <legend>Приоритет</legend>
          <div className="filter-toggle-row">
            {ALL_PRIORITIES.map((p) => (
              <label key={p} className="filter-pill">
                <input type="checkbox" checked={priority.includes(p)} onChange={() => toggle("priority", p, priority)} />
                {TASK_PRIORITY_LABELS[p]}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="filter-grid">
          {idSelect("assignee_id", "Исполнитель", personOptions)}
          {idSelect("creator_id", "Постановщик", personOptions)}
          {idSelect("university_id", "Учебное заведение", universities.data)}
          <label className="filter-field">
            Срок
            <select
              value={draft.deadline_preset ?? ""}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, deadline_preset: (e.target.value || undefined) as DeadlinePreset | undefined }))
              }
            >
              <option value="">Любой</option>
              {(Object.entries(DEADLINE_PRESET_LABELS) as [DeadlinePreset, string][]).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
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
