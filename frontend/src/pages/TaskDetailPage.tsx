import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft } from "lucide-react";
import { ApiError } from "../api/client";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, useTask, useUpdateTask, type TaskPriority } from "../api/tasks";
import { paths, taskPath } from "../app/navigation";
import { FieldError, FormFooter, formText } from "../components/forms/FormParts";
import { RefreshError, queryFallback } from "../components/QueryState";
import { TaskActivity } from "../components/tasks/TaskActivity";
import { TaskChecklist } from "../components/tasks/TaskChecklist";
import { TaskComments } from "../components/tasks/TaskComments";
import { TaskStatusActions } from "../components/tasks/TaskStatusActions";
import { TaskSubtasks } from "../components/tasks/TaskSubtasks";
import { formatFullDate } from "../lib/format";

function TaskEditForm({
  task,
  onDone,
}: {
  task: NonNullable<ReturnType<typeof useTask>["data"]>;
  onDone: () => void;
}) {
  const update = useUpdateTask(task.id);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const deadline = formText(f, "deadline");
    update.mutate(
      {
        version: task.version,
        title: formText(f, "title"),
        description: formText(f, "description"),
        deadline: deadline || null,
        priority: formText(f, "priority") as TaskPriority,
      },
      { onSuccess: onDone },
    );
  }
  return (
    <form onSubmit={submit} className="panel">
      <label>
        Название
        <input name="title" required maxLength={200} defaultValue={task.title} />
        <FieldError error={update.error} field="title" />
      </label>
      <label>
        Описание
        <textarea name="description" maxLength={4000} rows={3} defaultValue={task.description} />
        <FieldError error={update.error} field="description" />
      </label>
      <div className="form-row">
        <label>
          Срок
          <input name="deadline" type="date" defaultValue={task.deadline ?? ""} />
          <FieldError error={update.error} field="deadline" />
        </label>
        <label>
          Приоритет
          <select name="priority" defaultValue={task.priority}>
            {(Object.entries(TASK_PRIORITY_LABELS) as [TaskPriority, string][]).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <FormFooter error={update.error} pending={update.isPending} onCancel={onDone} submitLabel="Сохранить" />
    </form>
  );
}

export function TaskDetailPage() {
  const { id } = useParams();
  const taskId = Number(id);
  const [editing, setEditing] = useState(false);
  const task = useTask(taskId);

  if (task.error instanceof ApiError && task.error.status === 404) {
    return (
      <section className="panel">
        <div className="empty">
          <h2>Задача не найдена</h2>
          <p>Возможно, она архивирована или относится к вузу, который вам не назначен.</p>
          <Link className="text-button" to={paths.tasks}>
            К списку задач
          </Link>
        </div>
      </section>
    );
  }
  const fallback = queryFallback([task]);
  if (fallback || !task.data) return fallback;
  const t = task.data;

  return (
    <>
      <RefreshError queries={[task]} />
      <div className="detail-links">
        <Link className="back-link text-button" to={paths.tasks}>
          <ArrowLeft size={16} />
          К списку задач
        </Link>
      </div>
      {t.parent && (
        <p className="muted">
          Подзадача: <Link to={taskPath(t.parent.id)}>{t.parent.title}</Link>
        </p>
      )}
      {editing ? (
        <TaskEditForm task={t} onDone={() => setEditing(false)} />
      ) : (
        <section className="panel">
          <div className="section-head">
            <h2>{t.title}</h2>
            <button type="button" className="secondary" onClick={() => setEditing(true)}>
              Изменить
            </button>
          </div>
          <TaskStatusActions task={t} />
          <div className="detail-grid">
            <div>
              <small className="muted">Статус</small>
              <p>{TASK_STATUS_LABELS[t.status]}</p>
            </div>
            <div>
              <small className="muted">Приоритет</small>
              <p>{TASK_PRIORITY_LABELS[t.priority]}</p>
            </div>
            <div>
              <small className="muted">Срок</small>
              <p>{t.deadline ? formatFullDate(t.deadline) : "Без срока"}</p>
            </div>
            <div>
              <small className="muted">Плановое начало</small>
              <p>{t.planned_start ? formatFullDate(t.planned_start) : "—"}</p>
            </div>
            <div>
              <small className="muted">Создатель</small>
              <p>{t.creator?.full_name ?? "—"}</p>
            </div>
            <div>
              <small className="muted">Учебное заведение</small>
              <p>{t.university?.name ?? "—"}</p>
            </div>
            <div>
              <small className="muted">Взаимодействие</small>
              <p>{t.interaction?.program ?? "—"}</p>
            </div>
            <div>
              <small className="muted">Договор</small>
              <p>{t.contract?.contract_number ?? "—"}</p>
            </div>
          </div>
          {t.description && (
            <div>
              <small className="muted">Описание</small>
              <p>{t.description}</p>
            </div>
          )}
          <div>
            <small className="muted">Исполнители</small>
            <p>{t.assignees.length ? t.assignees.map((a) => a.full_name).join(", ") : "Не назначены"}</p>
          </div>
          {t.participants.length > 0 && (
            <div>
              <small className="muted">Со-исполнители</small>
              <p>{t.participants.map((a) => a.full_name).join(", ")}</p>
            </div>
          )}
          {t.observers.length > 0 && (
            <div>
              <small className="muted">Наблюдатели</small>
              <p>{t.observers.map((a) => a.full_name).join(", ")}</p>
            </div>
          )}
        </section>
      )}
      <section className="panel">
        <TaskActivity taskId={t.id} />
      </section>
      <section className="panel">
        <TaskChecklist taskId={t.id} items={t.checklist} />
      </section>
      {!t.parent && (
        <section className="panel">
          <TaskSubtasks taskId={t.id} />
        </section>
      )}
      <section className="panel">
        <TaskComments taskId={t.id} />
      </section>
    </>
  );
}
