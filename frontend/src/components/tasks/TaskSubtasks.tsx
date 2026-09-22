import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { taskPath } from "../../app/navigation";
import { useSession } from "../../app/AuthGate";
import {
  TASK_STATUS_LABELS,
  subtasksKey,
  useAssignableUsers,
  useCreateTask,
  useSetTaskAssignees,
  useSubtasks,
  type TaskListItem,
} from "../../api/tasks";
import { errorText } from "../../api/client";
import { seesAllActions } from "../../lib/user";

/** Inline responsible-user control for one subtask row: a select for whoever may reassign it (the
 * subtask's own creator, or a supervisor/admin — same rule as TaskAction.REASSIGN server-side), plain
 * read-only text for everyone else. */
function SubtaskAssignee({ parentId, subtask }: { parentId: number; subtask: TaskListItem }) {
  const { user } = useSession();
  const client = useQueryClient();
  const users = useAssignableUsers();
  const setAssignees = useSetTaskAssignees(subtask.id);
  const canReassign = seesAllActions(user.roles) || subtask.creator?.id === user.id;
  const current = subtask.assignees[0]?.id ?? "";

  if (!canReassign) {
    return <span className="muted">{subtask.assignees[0]?.full_name ?? "Без исполнителя"}</span>;
  }

  return (
    <select
      className="subtask-assignee-select"
      aria-label={`Ответственный за «${subtask.title}»`}
      value={current}
      disabled={setAssignees.isPending}
      onChange={(e) => {
        const value = e.target.value;
        setAssignees.mutate(value ? [Number(value)] : [], {
          onSuccess: () => void client.invalidateQueries({ queryKey: subtasksKey(parentId), exact: true }),
        });
      }}
    >
      <option value="">Без исполнителя</option>
      {users.data?.map((u) => (
        <option value={u.id} key={u.id}>
          {u.full_name}
        </option>
      ))}
    </select>
  );
}

export function TaskSubtasks({ taskId }: { taskId: number }) {
  const [title, setTitle] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const client = useQueryClient();
  const subtasks = useSubtasks(taskId);
  const users = useAssignableUsers();
  const create = useCreateTask();

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim()) return;
    create.mutate(
      { title: title.trim(), parent_task_id: taskId, assignee_ids: assigneeId ? [Number(assigneeId)] : [] },
      {
        onSuccess: () => {
          setTitle("");
          setAssigneeId("");
          void client.invalidateQueries({ queryKey: subtasksKey(taskId), exact: true });
        },
      },
    );
  }

  return (
    <div className="task-subtasks">
      <h3>Подзадачи</h3>
      <ul className="subtask-list">
        {subtasks.data?.map((t) => (
          <li key={t.id}>
            <Link className="subtask-title" to={taskPath(t.id)}>
              {t.title}
            </Link>
            <span className="subtask-meta">
              <span className={`badge badge-${t.status === "completed" ? "3" : "1"}`}>{TASK_STATUS_LABELS[t.status]}</span>
              <SubtaskAssignee parentId={taskId} subtask={t} />
            </span>
          </li>
        ))}
        {subtasks.data && !subtasks.data.length && <p className="empty">Подзадач пока нет.</p>}
      </ul>
      <form onSubmit={submit} className="checklist-add subtask-add">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Добавить подзадачу"
          maxLength={200}
          aria-label="Название подзадачи"
        />
        <select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} aria-label="Ответственный">
          <option value="">Без исполнителя</option>
          {users.data?.map((u) => (
            <option value={u.id} key={u.id}>
              {u.full_name}
            </option>
          ))}
        </select>
        <button type="submit" className="secondary" disabled={create.isPending || !title.trim()}>
          Добавить
        </button>
      </form>
      {create.isError && <p className="danger" role="alert">{errorText(create.error)}</p>}
    </div>
  );
}
