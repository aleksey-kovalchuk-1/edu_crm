import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { taskPath } from "../../app/navigation";
import { TASK_STATUS_LABELS, useCreateTask, useSubtasks } from "../../api/tasks";
import { errorText } from "../../api/client";

export function TaskSubtasks({ taskId }: { taskId: number }) {
  const [title, setTitle] = useState("");
  const client = useQueryClient();
  const subtasks = useSubtasks(taskId);
  const create = useCreateTask();

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim()) return;
    create.mutate(
      { title: title.trim(), parent_task_id: taskId },
      {
        onSuccess: () => {
          setTitle("");
          void client.invalidateQueries({ queryKey: ["tasks", "subtasks", taskId], exact: true });
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
            <Link to={taskPath(t.id)}>{t.title}</Link>
            <span className={`badge badge-${t.status === "completed" ? "3" : "1"}`}>{TASK_STATUS_LABELS[t.status]}</span>
          </li>
        ))}
        {subtasks.data && !subtasks.data.length && <p className="empty">Подзадач пока нет.</p>}
      </ul>
      <form onSubmit={submit} className="checklist-add">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Добавить подзадачу"
          maxLength={200}
          aria-label="Название подзадачи"
        />
        <button type="submit" className="secondary" disabled={create.isPending || !title.trim()}>
          Добавить
        </button>
      </form>
      {create.isError && <p className="danger" role="alert">{errorText(create.error)}</p>}
    </div>
  );
}
