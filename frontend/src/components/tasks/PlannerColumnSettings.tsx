import { ArrowLeft, ArrowRight } from "lucide-react";
import { PLANNER_STATUSES, TASK_STATUS_LABELS, type TaskStatus } from "../../api/tasks";

/** Which planner columns are shown and in what order — a native <details> disclosure like
 * TaskColumnPicker, keyboard-operable with no extra JS. */
export function PlannerColumnSettings({
  columns,
  onChange,
}: {
  columns: TaskStatus[];
  onChange: (columns: TaskStatus[]) => void;
}) {
  function toggle(status: TaskStatus) {
    onChange(columns.includes(status) ? columns.filter((s) => s !== status) : [...columns, status]);
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= columns.length) return;
    const next = [...columns];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <details className="column-picker">
      <summary>Колонки плана</summary>
      <div className="column-picker-menu planner-column-settings">
        {PLANNER_STATUSES.map((status) => {
          const index = columns.indexOf(status);
          const visible = index !== -1;
          const label = TASK_STATUS_LABELS[status];
          return (
            <div className="planner-column-setting" key={status}>
              <label className="toggle">
                <input type="checkbox" checked={visible} onChange={() => toggle(status)} />
                {label}
              </label>
              {visible && (
                <span className="planner-column-setting-order">
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Сдвинуть колонку «${label}» левее`}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    <ArrowLeft size={13} />
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Сдвинуть колонку «${label}» правее`}
                    disabled={index === columns.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    <ArrowRight size={13} />
                  </button>
                </span>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}
