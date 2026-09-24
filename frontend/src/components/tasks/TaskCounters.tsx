import { useTaskCounters, type TaskCounters as Counters, type TaskScope } from "../../api/tasks";
import type { FilterPatch } from "./taskFilterState";

/** Quick filters with live counts (Bitrix24-style counters). Each chip toggles one URL filter. */
const CHIPS: { key: keyof Counters; label: string; param: string; value: string; tone: string }[] = [
  { key: "open", label: "Открытые", param: "active", value: "true", tone: "neutral" },
  { key: "overdue", label: "Просрочено", param: "deadline_preset", value: "overdue", tone: "danger" },
  { key: "due_today", label: "Сегодня", param: "deadline_preset", value: "today", tone: "warning" },
  { key: "awaiting_review", label: "На проверке", param: "status", value: "awaiting_review", tone: "info" },
  { key: "no_deadline", label: "Без срока", param: "deadline_preset", value: "no_deadline", tone: "neutral" },
];

export function TaskCounters({
  scope,
  params,
  onSelect,
}: {
  scope: TaskScope;
  params: URLSearchParams;
  onSelect: (patch: FilterPatch) => void;
}) {
  const counters = useTaskCounters(scope);
  if (!counters.data) return null;
  const data = counters.data;
  return (
    <div className="task-counters" role="group" aria-label="Быстрые фильтры">
      {CHIPS.map((c) => {
        const pressed = params.getAll(c.param).includes(c.value);
        const count = data[c.key];
        return (
          <button
            key={c.key}
            type="button"
            className={`counter-chip tone-${c.tone}${count === 0 ? " is-empty" : ""}`}
            aria-pressed={pressed}
            onClick={() => onSelect({ [c.param]: pressed ? null : c.value })}
          >
            <span>{c.label}</span>
            <strong>{count}</strong>
          </button>
        );
      })}
    </div>
  );
}
