import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrentUser } from "../../api/auth";
import type { LaunchTasksResponse } from "../../api/launchTasks";
import {
  MANAGER_TRANSITIONS,
  NEEDS_COMMENT,
  NEXT_STATUSES,
  TASK_STATUS_LABELS,
  useAssignableUsers,
  useChangeTaskStatus,
  useSetTaskMembers,
  useTask,
  useUpdateTask,
  type Task,
  type TaskPatchInput,
  type TaskStatus,
} from "../../api/tasks";
import { ROLES } from "../../lib/user";
import { Modal } from "../Modal";
import { queryFallback } from "../QueryState";
import { FieldError, FormFooter, formText } from "../forms/FormParts";

const sameIds = (a: number[], b: number[]) => a.length === b.length && a.every((id, i) => id === b[i]);
const idsOf = (people: { id: number }[]) => people.map((p) => p.id).sort((x, y) => x - y);

/** Checkbox list of everyone assignable, named by its legend. */
function PeopleField({
  legend,
  name,
  chosen,
  disabled,
}: {
  legend: string;
  name: string;
  chosen: number[];
  disabled: boolean;
}) {
  const people = useAssignableUsers();
  return (
    <fieldset className="filter-fieldset" disabled={disabled}>
      <legend>{legend}</legend>
      <div className="assignee-picker-list">
        {people.data?.map((p) => (
          <label key={p.id} className="toggle">
            <input type="checkbox" name={name} value={p.id} defaultChecked={chosen.includes(p.id)} />
            {p.full_name}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * Title, deadline, people and status of one task, saved in that order with each step using the version
 * the previous one returned. Only what changed is sent. Title, deadline and people follow the server's
 * rule (task_policy.py): the task's author or a supervisor/admin. Status moves follow TRANSITIONS in
 * task_routes.py: an assignee may also make the forward ones.
 */
function TaskEditForm({ task, launchId, close }: { task: Task; launchId: number; close: () => void }) {
  const client = useQueryClient();
  const me = useCurrentUser().data?.user;
  const update = useUpdateTask(task.id);
  const members = useSetTaskMembers(task.id);
  const status = useChangeTaskStatus(task.id);
  const [toStatus, setToStatus] = useState<TaskStatus>(task.status);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const roles = me?.roles ?? [];
  const canEdit = roles.includes(ROLES.supervisor) || roles.includes(ROLES.admin) || (!!me && task.creator?.id === me.id);
  const isAssignee = !!me && task.assignees.some((a) => a.id === me.id);
  const nextStatuses = NEXT_STATUSES[task.status].filter((to) => {
    if (to === "awaiting_review" && !task.approval_required) return false;
    if (to === "completed" && task.status === "in_progress" && task.approval_required) return false;
    return canEdit || (isAssignee && !MANAGER_TRANSITIONS.has(`${task.status}:${to}`));
  });
  const needsComment = NEEDS_COMMENT.has(`${task.status}:${toStatus}`);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setPending(true);
    setError(null);
    let version = task.version;
    try {
      if (canEdit) {
        const patch: TaskPatchInput = { version };
        const title = formText(f, "title").trim();
        const deadline = formText(f, "deadline") || null;
        if (title && title !== task.title) patch.title = title;
        if (deadline !== task.deadline) patch.deadline = deadline;
        if (Object.keys(patch).length > 1) version = (await update.mutateAsync(patch)).version;

        const assignees = f.getAll("assignee_ids").map(Number).sort((a, b) => a - b);
        const participants = f.getAll("participant_ids").map(Number).sort((a, b) => a - b);
        if (!sameIds(assignees, idsOf(task.assignees)) || !sameIds(participants, idsOf(task.participants))) {
          const saved = await members.mutateAsync({
            assignee_ids: assignees,
            participant_ids: participants,
            observer_ids: task.observers.map((o) => o.id),
          });
          version = saved.version;
        }
      }
      if (toStatus !== task.status) {
        await status.mutateAsync({ to_status: toStatus, comment: formText(f, "comment"), version });
      }
      close();
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
      void client.invalidateQueries({ queryKey: ["launches", launchId, "tasks"] });
    }
  }

  return (
    <form onSubmit={submit}>
      {!canEdit && (
        <p className="muted">Название, срок и участников может менять автор задачи или руководитель.</p>
      )}
      {!nextStatuses.length && !canEdit && (
        <p className="muted">Статус может менять исполнитель, автор задачи или руководитель.</p>
      )}
      <label>
        Название
        <input name="title" required maxLength={200} defaultValue={task.title} disabled={!canEdit} />
        <FieldError error={error} field="title" />
      </label>
      <div className="form-row">
        <label>
          Срок
          <input name="deadline" type="date" defaultValue={task.deadline ?? ""} disabled={!canEdit} required={!!task.deadline} />
          <FieldError error={error} field="deadline" />
        </label>
        <label>
          Статус
          <select value={toStatus} onChange={(e) => setToStatus(e.target.value as TaskStatus)} disabled={!nextStatuses.length}>
            <option value={task.status}>{TASK_STATUS_LABELS[task.status]}</option>
            {nextStatuses.map((s) => (
              <option value={s} key={s}>
                {TASK_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {needsComment && (
        <label>
          Что нужно исправить
          <textarea name="comment" required maxLength={2000} rows={3} />
        </label>
      )}
      <div className="form-row">
        <PeopleField legend="Исполнители" name="assignee_ids" chosen={idsOf(task.assignees)} disabled={!canEdit} />
        <PeopleField legend="Участники" name="participant_ids" chosen={idsOf(task.participants)} disabled={!canEdit} />
      </div>
      <FormFooter error={error} pending={pending} onCancel={close} submitLabel="Сохранить" />
    </form>
  );
}

function LoadedTaskEditForm({ taskId, launchId, close }: { taskId: number; launchId: number; close: () => void }) {
  const task = useTask(taskId);
  // The people checkboxes must exist before the form can be saved: a save without them would read as
  // "nobody assigned" and clear the task's assignees and participants.
  const people = useAssignableUsers();
  const fallback = queryFallback([task, people]);
  if (fallback || !task.data || !people.data) return fallback;
  return <TaskEditForm task={task.data} launchId={launchId} close={close} />;
}

/**
 * «Изменить задачу» on an interaction's page: opened from a task row with that task chosen, or from the
 * header button with a picker over the interaction's tasks grouped by stage.
 */
export function LaunchTaskEditDialog({
  launchId,
  tasks,
  initialTaskId,
  close,
}: {
  launchId: number;
  tasks: LaunchTasksResponse;
  initialTaskId?: number;
  close: () => void;
}) {
  const [taskId, setTaskId] = useState<number | null>(initialTaskId ?? null);
  const groups = [
    ...tasks.categories.filter((c) => c.tasks.length).map((c) => ({ key: `c${c.index}`, name: c.name, tasks: c.tasks })),
    ...(tasks.uncategorized.length ? [{ key: "none", name: "Без категории", tasks: tasks.uncategorized }] : []),
  ];

  return (
    <Modal title="Изменить задачу" close={close} wide>
      {initialTaskId === undefined && (
        <label>
          Задача
          <select value={taskId ?? ""} onChange={(e) => setTaskId(e.target.value ? Number(e.target.value) : null)}>
            <option value="" disabled>
              Выберите задачу
            </option>
            {groups.map((g) => (
              <optgroup label={g.name} key={g.key}>
                {g.tasks.map((t) => (
                  <option value={t.id} key={t.id}>
                    {t.title}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
      )}
      {taskId !== null && <LoadedTaskEditForm key={taskId} taskId={taskId} launchId={launchId} close={close} />}
    </Modal>
  );
}
