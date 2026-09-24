import { X } from "lucide-react";
import { useUniversities } from "../../api/catalogs";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, useAssignableUsers, type DeadlinePreset, type TaskPriority, type TaskStatus } from "../../api/tasks";
import { DEADLINE_PRESET_LABELS } from "./TaskFilterDialog";
import { CLEAR_FILTERS, type FilterPatch } from "./taskFilterState";

/**
 * The applied filters as removable chips, shown inside the search bar. Editing happens in
 * TaskFilterDialog; this only ever removes.
 */
export function TaskFilterSummary({
  params,
  onUpdate,
}: {
  params: URLSearchParams;
  onUpdate: (patch: FilterPatch) => void;
}) {
  const universities = useUniversities();
  const people = useAssignableUsers();
  const status = params.getAll("status");
  const priority = params.getAll("priority");
  const personName = (id: string) => people.data?.find((p) => String(p.id) === id)?.full_name ?? id;
  const single = (key: string, label: (value: string) => string) => {
    const value = params.get(key);
    return value ? [{ label: label(value), clear: { [key]: null } as FilterPatch }] : [];
  };

  const chips: { label: string; clear: FilterPatch }[] = [
    ...status.map((s) => ({ label: `Статус: ${TASK_STATUS_LABELS[s as TaskStatus] ?? s}`, clear: { status: status.filter((v) => v !== s) } })),
    ...priority.map((p) => ({ label: `Приоритет: ${TASK_PRIORITY_LABELS[p as TaskPriority] ?? p}`, clear: { priority: priority.filter((v) => v !== p) } })),
    ...single("assignee_id", (id) => `Исполнитель: ${personName(id)}`),
    ...single("creator_id", (id) => `Постановщик: ${personName(id)}`),
    ...single("university_id", (id) => `Вуз: ${universities.data?.find((u) => String(u.id) === id)?.name ?? id}`),
    ...single("deadline_preset", (v) => DEADLINE_PRESET_LABELS[v as DeadlinePreset] ?? v),
    ...single("active", (v) => (v === "true" ? "Только открытые" : "Только завершённые")),
    ...single("has_checklist", (v) => (v === "true" ? "С чек-листом" : "Без чек-листа")),
  ];

  if (!chips.length) return null;

  return (
    <>
      {chips.map((c) => (
        <button
          key={c.label}
          type="button"
          className="filter-chip"
          aria-label={`${c.label} — убрать фильтр`}
          onClick={() => onUpdate(c.clear)}
        >
          {c.label}
          <X size={12} aria-hidden="true" />
        </button>
      ))}
      {chips.length > 1 && (
        <button type="button" className="text-button filter-clear" onClick={() => onUpdate(CLEAR_FILTERS)}>
          Сбросить все
        </button>
      )}
    </>
  );
}
