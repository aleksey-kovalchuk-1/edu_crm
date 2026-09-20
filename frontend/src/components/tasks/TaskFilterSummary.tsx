import { X } from "lucide-react";
import { useUniversities } from "../../api/catalogs";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, type DeadlinePreset, type TaskPriority, type TaskStatus } from "../../api/tasks";
import type { FilterPatch } from "./taskFilterState";

const DEADLINE_PRESET_LABELS: Record<DeadlinePreset, string> = {
  overdue: "Просрочено",
  today: "Сегодня",
  this_week: "На этой неделе",
  next_week: "На следующей неделе",
  no_deadline: "Без срока",
};

/**
 * Compact, removable summary of the filters currently applied to the URL — replaces the old permanent
 * inline panel (docs/decisions.md). Editing filters happens in TaskFilterDialog; this only ever removes.
 */
export function TaskFilterSummary({
  params,
  onUpdate,
}: {
  params: URLSearchParams;
  onUpdate: (patch: FilterPatch) => void;
}) {
  const universities = useUniversities();
  const status = params.getAll("status");
  const priority = params.getAll("priority");
  const universityId = params.get("university_id") ?? "";
  const deadlinePreset = params.get("deadline_preset") ?? "";
  const active = params.get("active") ?? "";
  const hasChecklist = params.get("has_checklist") ?? "";

  const chips: { label: string; clear: FilterPatch }[] = [
    ...status.map((s) => ({ label: `Статус: ${TASK_STATUS_LABELS[s as TaskStatus] ?? s}`, clear: { status: status.filter((v) => v !== s) } })),
    ...priority.map((p) => ({ label: `Приоритет: ${TASK_PRIORITY_LABELS[p as TaskPriority] ?? p}`, clear: { priority: priority.filter((v) => v !== p) } })),
    ...(universityId
      ? [{ label: `Вуз: ${universities.data?.find((u) => String(u.id) === universityId)?.name ?? universityId}`, clear: { university_id: null } }]
      : []),
    ...(deadlinePreset ? [{ label: DEADLINE_PRESET_LABELS[deadlinePreset as DeadlinePreset] ?? deadlinePreset, clear: { deadline_preset: null } }] : []),
    ...(active ? [{ label: active === "true" ? "Только активные" : "Только завершённые", clear: { active: null } }] : []),
    ...(hasChecklist ? [{ label: hasChecklist === "true" ? "С чек-листом" : "Без чек-листа", clear: { has_checklist: null } }] : []),
  ];

  if (!chips.length) return null;

  return (
    <div className="filter-summary">
      {chips.map((c) => (
        <button key={c.label} type="button" className="filter-chip" onClick={() => onUpdate(c.clear)}>
          {c.label}
          <X size={12} />
        </button>
      ))}
      {chips.length > 1 && (
        <button
          type="button"
          className="text-button"
          onClick={() =>
            onUpdate({ status: [], priority: [], university_id: null, deadline_preset: null, active: null, has_checklist: null })
          }
        >
          Сбросить все
        </button>
      )}
    </div>
  );
}
