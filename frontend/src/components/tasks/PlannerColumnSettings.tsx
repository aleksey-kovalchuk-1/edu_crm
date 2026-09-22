import { PLANNER_STATUSES, TASK_STATUS_LABELS, type TaskStatus } from "../../api/tasks";

/**
 * Which system status columns are shown on "Мой план" — a native <details> disclosure like
 * TaskColumnPicker, keyboard-operable with no extra JS. Custom columns aren't listed here (they're
 * always shown — hiding one you created would be more confusing than useful); they're created, renamed,
 * deleted and reordered directly on the board (BoardColumnHeader/AddBoardColumn), which also handles
 * reordering system columns relative to custom ones.
 */
export function PlannerColumnSettings({
  columns,
  onChange,
}: {
  columns: string[];
  onChange: (columns: string[]) => void;
}) {
  function toggle(status: TaskStatus) {
    onChange(columns.includes(status) ? columns.filter((s) => s !== status) : [...columns, status]);
  }

  return (
    <details className="column-picker">
      <summary>Колонки плана</summary>
      <div className="column-picker-menu planner-column-settings">
        {PLANNER_STATUSES.map((status) => (
          <label className="toggle" key={status}>
            <input type="checkbox" checked={columns.includes(status)} onChange={() => toggle(status)} />
            {TASK_STATUS_LABELS[status]}
          </label>
        ))}
      </div>
    </details>
  );
}
