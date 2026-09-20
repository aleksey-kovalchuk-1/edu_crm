import { X } from "lucide-react";
import { useUniversities } from "../../api/catalogs";
import {
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
  type DeadlinePreset,
  type TaskPriority,
  type TaskStatus,
} from "../../api/tasks";

export type FilterPatch = Record<string, string | string[] | null>;

const DEADLINE_PRESET_LABELS: Record<DeadlinePreset, string> = {
  overdue: "Просрочено",
  today: "Сегодня",
  this_week: "На этой неделе",
  next_week: "На следующей неделе",
  no_deadline: "Без срока",
};

const PRESETS: { label: string; params: FilterPatch }[] = [
  { label: "Просрочено", params: { deadline_preset: "overdue" } },
  { label: "Срок сегодня", params: { deadline_preset: "today" } },
  { label: "Ожидает меня", params: { scope: "mine", status: ["new", "in_progress", "awaiting_review"] } },
  { label: "Созданные мной", params: { scope: "created" } },
  { label: "Без срока", params: { deadline_preset: "no_deadline" } },
];

const ALL_STATUSES = Object.keys(TASK_STATUS_LABELS) as TaskStatus[];
const ALL_PRIORITIES = Object.keys(TASK_PRIORITY_LABELS) as TaskPriority[];

/** A plain panel (not a popover) with presets, filter controls and removable chips for what's active. */
export function TaskFilterBar({
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

  function toggle(key: "status" | "priority", value: string, current: string[]) {
    onUpdate({ [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] });
  }

  return (
    <div className="task-filter-bar">
      <div className="filter-presets">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" className="secondary" onClick={() => onUpdate(p.params)}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="filter-controls">
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
          <select value={universityId} onChange={(e) => onUpdate({ university_id: e.target.value || null })}>
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
          <select value={active} onChange={(e) => onUpdate({ active: e.target.value || null })}>
            <option value="">Все</option>
            <option value="true">Только активные</option>
            <option value="false">Только завершённые</option>
          </select>
        </label>
        <label className="inline-select">
          Чек-лист
          <select value={hasChecklist} onChange={(e) => onUpdate({ has_checklist: e.target.value || null })}>
            <option value="">Не важно</option>
            <option value="true">С чек-листом</option>
            <option value="false">Без чек-листа</option>
          </select>
        </label>
      </div>
      {chips.length > 0 && (
        <div className="filter-chips">
          {chips.map((c) => (
            <button key={c.label} type="button" className="filter-chip" onClick={() => onUpdate(c.clear)}>
              {c.label}
              <X size={12} />
            </button>
          ))}
          <button
            type="button"
            className="text-button"
            onClick={() =>
              onUpdate({ status: [], priority: [], university_id: null, deadline_preset: null, active: null, has_checklist: null })
            }
          >
            Сбросить фильтры
          </button>
        </div>
      )}
    </div>
  );
}
