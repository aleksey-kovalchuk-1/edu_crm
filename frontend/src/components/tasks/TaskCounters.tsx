import { useTaskCounters, type TaskCounters as Counters, type TaskScope } from "../../api/tasks";

const TILES: { key: keyof Counters; label: string; params: Record<string, string> }[] = [
  { key: "open", label: "Открытых", params: { active: "true" } },
  { key: "overdue", label: "Просрочено", params: { deadline_preset: "overdue" } },
  { key: "due_today", label: "Срок сегодня", params: { deadline_preset: "today" } },
  { key: "awaiting_review", label: "На проверке", params: { status: "awaiting_review" } },
  { key: "no_deadline", label: "Без срока", params: { deadline_preset: "no_deadline" } },
];

export function TaskCounters({
  scope,
  onSelect,
}: {
  scope: TaskScope;
  onSelect: (params: Record<string, string | null>) => void;
}) {
  const counters = useTaskCounters(scope);
  if (!counters.data) return null;
  const data = counters.data;
  return (
    <div className="task-counters">
      {TILES.map((t) => (
        <button key={t.key} type="button" className="counter-tile" onClick={() => onSelect(t.params)}>
          <strong>{data[t.key]}</strong>
          <span>{t.label}</span>
        </button>
      ))}
    </div>
  );
}
