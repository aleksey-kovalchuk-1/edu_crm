import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, useUpdateTask, type Task, type TaskPatchInput, type TaskPriority } from "../../api/tasks";
import type { PersonRef } from "../../api/types";
import { launchPath, universityPath } from "../../app/navigation";
import { formatDateTime, initials } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { TaskAssigneePicker } from "./TaskAssigneePicker";
import { InlineError } from "./TaskInlineText";
import { STATUS_BADGE, deadlineInfo } from "./taskDisplay";

function Field({ label, children, action }: { label: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="task-field">
      <div className="task-field-label">
        <span>{label}</span>
        {action}
      </div>
      <div className="task-field-value">{children}</div>
    </div>
  );
}

function PeopleList({ people, empty }: { people: PersonRef[]; empty: string }) {
  if (!people.length) return <span className="muted">{empty}</span>;
  return (
    <ul className="task-people">
      {people.map((p) => (
        <li key={p.id}>
          <span className="avatar avatar-sm" aria-hidden="true">
            {initials(p.full_name)}
          </span>
          {p.full_name}
        </li>
      ))}
    </ul>
  );
}

/**
 * Every property of the task in one column, each editable in place where the API allows it
 * (PATCH /tasks/{id} for dates, priority and review; PATCH /tasks/{id}/assignees for assignees).
 * The server stays the authority on permissions — a refused edit shows its error inline.
 */
export function TaskSidebar({ task }: { task: Task }) {
  const update = useUpdateTask(task.id);
  const [editingAssignees, setEditingAssignees] = useState(false);
  const now = useNow();
  const deadline = deadlineInfo(task.deadline, task.status, new Date(now));
  const save = (patch: Omit<TaskPatchInput, "version">) => update.mutate({ version: task.version, ...patch });

  return (
    <aside className="task-sidebar panel" aria-label="Свойства задачи">
      <Field label="Статус">
        <span className={STATUS_BADGE[task.status]}>{TASK_STATUS_LABELS[task.status]}</span>
      </Field>
      <Field label="Срок">
        <input
          type="date"
          aria-label="Срок"
          value={task.deadline ?? ""}
          disabled={update.isPending}
          onChange={(e) => save({ deadline: e.target.value || null })}
        />
        {task.deadline && deadline.tone !== "neutral" && deadline.tone !== "muted" && (
          <span className={`deadline-pill tone-${deadline.tone}`}>{deadline.label}</span>
        )}
      </Field>
      <Field label="Плановое начало">
        <input
          type="date"
          aria-label="Плановое начало"
          value={task.planned_start ?? ""}
          disabled={update.isPending}
          onChange={(e) => save({ planned_start: e.target.value || null })}
        />
      </Field>
      <Field label="Приоритет">
        <select
          aria-label="Приоритет"
          value={task.priority}
          disabled={update.isPending}
          onChange={(e) => save({ priority: e.target.value as TaskPriority })}
        >
          {(Object.entries(TASK_PRIORITY_LABELS) as [TaskPriority, string][]).map(([value, label]) => (
            <option value={value} key={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <label className="toggle task-field-toggle">
        <input
          type="checkbox"
          checked={task.approval_required}
          disabled={update.isPending}
          onChange={(e) => save({ approval_required: e.target.checked })}
        />
        Требует проверки постановщиком
      </label>
      <InlineError error={update.error} />

      <hr />
      <Field
        label="Исполнители"
        action={
          !editingAssignees && (
            <button type="button" className="text-button" onClick={() => setEditingAssignees(true)}>
              Изменить
            </button>
          )
        }
      >
        {editingAssignees ? (
          <TaskAssigneePicker task={task} onDone={() => setEditingAssignees(false)} />
        ) : (
          <PeopleList people={task.assignees} empty="Не назначены" />
        )}
      </Field>
      {task.participants.length > 0 && (
        <Field label="Со-исполнители">
          <PeopleList people={task.participants} empty="—" />
        </Field>
      )}
      {task.observers.length > 0 && (
        <Field label="Наблюдатели">
          <PeopleList people={task.observers} empty="—" />
        </Field>
      )}
      <Field label="Постановщик">
        <PeopleList people={task.creator ? [task.creator] : []} empty="—" />
      </Field>

      <hr />
      <Field label="Учебное заведение">
        {task.university ? <Link to={universityPath(task.university.id)}>{task.university.name}</Link> : <span className="muted">—</span>}
      </Field>
      <Field label="Взаимодействие">
        {task.interaction ? (
          <Link to={launchPath(task.interaction.id)}>{task.interaction.program}</Link>
        ) : (
          <span className="muted">—</span>
        )}
      </Field>
      {task.contract && <Field label="Договор">{task.contract.contract_number}</Field>}

      <hr />
      <dl className="task-dates">
        <dt>Создана</dt>
        <dd>{formatDateTime(task.created_at)}</dd>
        <dt>Изменена</dt>
        <dd>{formatDateTime(task.updated_at)}</dd>
      </dl>
    </aside>
  );
}
