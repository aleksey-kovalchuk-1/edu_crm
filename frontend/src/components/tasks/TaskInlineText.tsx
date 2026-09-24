import { useState, type KeyboardEvent } from "react";
import { Pencil } from "lucide-react";
import { useUpdateTask, type Task } from "../../api/tasks";
import { errorText } from "../../api/client";

/** Any failed inline save (validation, permission, a version conflict) in one short line. */
export function InlineError({ error }: { error: unknown }) {
  return error ? (
    <p className="danger inline-error" role="alert">
      {errorText(error)}
    </p>
  ) : null;
}

/** Title as the page heading; the pencil turns it into an input. Enter or leaving the field saves, Escape cancels. */
export function TaskInlineTitle({ task }: { task: Task }) {
  const update = useUpdateTask(task.id);
  const [draft, setDraft] = useState<string | null>(null);

  function save() {
    // Enter disables the input while saving, which can fire blur → a second save; ignore it.
    if (draft === null || update.isPending) return;
    const value = draft.trim();
    if (!value || value === task.title) return setDraft(null);
    update.mutate({ version: task.version, title: value }, { onSuccess: () => setDraft(null) });
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      save();
    } else if (e.key === "Escape") {
      setDraft(null);
      update.reset();
    }
  }

  if (draft !== null) {
    return (
      <div className="task-title-edit">
        <input
          className="task-title-input"
          aria-label="Название"
          value={draft}
          maxLength={200}
          autoFocus
          disabled={update.isPending}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          onKeyDown={onKeyDown}
        />
        <InlineError error={update.error} />
      </div>
    );
  }
  return (
    <div className="task-title-row">
      <h2 className="task-title">{task.title}</h2>
      <button type="button" className="icon-button" aria-label="Изменить название" onClick={() => setDraft(task.title)}>
        <Pencil size={16} />
      </button>
    </div>
  );
}

/** Description shown as text; «Изменить» swaps in a textarea with explicit Save/Cancel (multi-line text shouldn't save on blur). */
export function TaskInlineDescription({ task }: { task: Task }) {
  const update = useUpdateTask(task.id);
  const [draft, setDraft] = useState<string | null>(null);

  if (draft !== null) {
    return (
      <form
        className="task-description-edit"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate({ version: task.version, description: draft.trim() }, { onSuccess: () => setDraft(null) });
        }}
      >
        <textarea
          aria-label="Описание"
          value={draft}
          rows={5}
          maxLength={4000}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
        />
        <InlineError error={update.error} />
        <div className="task-description-actions">
          <button type="submit" className="primary" disabled={update.isPending}>
            Сохранить
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setDraft(null);
              update.reset();
            }}
          >
            Отмена
          </button>
        </div>
      </form>
    );
  }
  return (
    <div className="task-description">
      {task.description ? (
        <p>{task.description}</p>
      ) : (
        <p className="muted">Описания пока нет.</p>
      )}
      <button type="button" className="text-button" onClick={() => setDraft(task.description)}>
        <Pencil size={14} />
        {task.description ? "Изменить описание" : "Добавить описание"}
      </button>
    </div>
  );
}
