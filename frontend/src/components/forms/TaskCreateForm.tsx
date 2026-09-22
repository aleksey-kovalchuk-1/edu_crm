import { useState, type FormEvent } from "react";
import { useUniversities } from "../../api/catalogs";
import { useLaunches } from "../../api/queries";
import {
  TASK_PRIORITY_LABELS,
  useAssignableUsers,
  useCreateTask,
  type Task,
  type TaskPriority,
} from "../../api/tasks";
import { FieldError, FormFooter, formText } from "./FormParts";

export function TaskCreateForm({
  onCreated,
  onCancel,
  initialDeadline,
  initialUniversityId,
  initialLaunchId,
}: {
  onCreated: (task: Task) => void;
  onCancel: () => void;
  /** Prefills the deadline field (e.g. from the Deadlines board's per-column "+" — D-205's mapping);
   * the user can still change or clear it before creating. */
  initialDeadline?: string | null;
  /** When set (e.g. opened from an Interaction page), the University/Interaction fields are
   * pre-filled and locked — a task created from that page always belongs to that Interaction. */
  initialUniversityId?: number;
  initialLaunchId?: number;
}) {
  const [universityId, setUniversityId] = useState(initialUniversityId ? String(initialUniversityId) : "");
  const locked = initialUniversityId !== undefined;
  const users = useAssignableUsers();
  const universities = useUniversities();
  const launches = useLaunches();
  const create = useCreateTask();

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const deadline = formText(f, "deadline");
    const launchId = locked ? initialLaunchId : formText(f, "launch_id");
    create.mutate(
      {
        title: formText(f, "title"),
        description: formText(f, "description"),
        deadline: deadline || null,
        priority: formText(f, "priority") as TaskPriority,
        university_id: universityId ? Number(universityId) : null,
        launch_id: launchId ? Number(launchId) : null,
        assignee_ids: f.getAll("assignee_ids").map(Number),
      },
      { onSuccess: onCreated },
    );
  }

  const universityLaunches = universityId
    ? launches.data?.filter((l) => l.university_id === Number(universityId))
    : [];

  return (
    <form onSubmit={submit}>
      <label>
        Название
        <input name="title" required maxLength={200} placeholder="Например, собрать документы" autoFocus />
        <FieldError error={create.error} field="title" />
      </label>
      <label>
        Описание
        <textarea name="description" maxLength={4000} rows={2} placeholder="Необязательно" />
        <FieldError error={create.error} field="description" />
      </label>
      <div className="form-row">
        <label>
          Срок
          <input name="deadline" type="date" defaultValue={initialDeadline ?? ""} />
          <FieldError error={create.error} field="deadline" />
        </label>
        <label>
          Приоритет
          <select name="priority" defaultValue="normal">
            {(Object.entries(TASK_PRIORITY_LABELS) as [TaskPriority, string][]).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Исполнители
        <select
          name="assignee_ids"
          multiple
          size={Math.min(Math.max(users.data?.length ?? 1, 1), 5)}
        >
          {users.data?.map((u) => (
            <option value={u.id} key={u.id}>
              {u.full_name}
            </option>
          ))}
        </select>
        <FieldError error={create.error} field="assignee_ids" />
      </label>
      <label>
        Учебное заведение
        {locked ? (
          <span className="muted">
            {universities.data?.find((u) => u.id === initialUniversityId)?.name ?? initialUniversityId}
          </span>
        ) : (
          <select
            name="university_id"
            value={universityId}
            onChange={(e) => setUniversityId(e.target.value)}
          >
            <option value="">Без учебного заведения</option>
            {universities.data?.map((u) => (
              <option value={u.id} key={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        )}
        <FieldError error={create.error} field="university_id" />
      </label>
      {universityId && (
        <label>
          Взаимодействие
          {locked ? (
            <span className="muted">
              {launches.data?.find((l) => l.id === initialLaunchId)?.program ?? initialLaunchId}
            </span>
          ) : (
            <select name="launch_id" defaultValue="">
              <option value="">Без взаимодействия</option>
              {universityLaunches?.map((l) => (
                <option value={l.id} key={l.id}>
                  {l.program}
                </option>
              ))}
            </select>
          )}
          <FieldError error={create.error} field="launch_id" />
        </label>
      )}
      <FormFooter error={create.error} pending={create.isPending} onCancel={onCancel} />
    </form>
  );
}
