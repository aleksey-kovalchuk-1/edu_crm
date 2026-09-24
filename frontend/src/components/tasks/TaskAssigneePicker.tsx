import { useState } from "react";
import { useAssignableUsers, useSetTaskAssignees, type Task } from "../../api/tasks";
import { InlineError } from "./TaskInlineText";

/** Checkbox list of everyone assignable; «Сохранить» replaces the task's assignees (participants/observers untouched). */
export function TaskAssigneePicker({ task, onDone }: { task: Task; onDone: () => void }) {
  const people = useAssignableUsers();
  const save = useSetTaskAssignees(task.id);
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(task.assignees.map((a) => a.id)));

  function toggle(id: number) {
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <form
      className="assignee-picker"
      aria-label="Исполнители задачи"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate([...chosen], { onSuccess: onDone });
      }}
    >
      <div className="assignee-picker-list">
        {people.data?.map((p) => (
          <label key={p.id} className="toggle">
            <input type="checkbox" checked={chosen.has(p.id)} onChange={() => toggle(p.id)} />
            {p.full_name}
          </label>
        ))}
      </div>
      <InlineError error={save.error} />
      <div className="task-description-actions">
        <button type="submit" className="primary" disabled={save.isPending}>
          Сохранить
        </button>
        <button type="button" className="secondary" onClick={onDone}>
          Отмена
        </button>
      </div>
    </form>
  );
}
