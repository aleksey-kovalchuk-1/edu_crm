import { useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { errorText } from "../../api/client";
import { useCreateTask } from "../../api/tasks";

/**
 * One-line task creation at the top of the list (Bitrix24 / Asana style): type a title, press
 * Enter. The task is assigned to the current user so it lands in «Мои задачи» straight away;
 * everything else is filled in later on the task itself, or via «Создать задачу» for the full form.
 */
export function TaskQuickAdd({ userId }: { userId: number }) {
  const [title, setTitle] = useState("");
  const create = useCreateTask();

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = title.trim();
    if (!value || create.isPending) return;
    create.mutate({ title: value, assignee_ids: [userId] }, { onSuccess: () => setTitle("") });
  }

  return (
    <form className="task-quick-add" onSubmit={submit}>
      <Plus size={16} aria-hidden="true" />
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Быстрая задача — введите название и нажмите Enter"
        aria-label="Быстрая задача"
        maxLength={200}
        disabled={create.isPending}
      />
      {create.error && (
        <span className="danger" role="alert">
          {errorText(create.error)}
        </span>
      )}
    </form>
  );
}
