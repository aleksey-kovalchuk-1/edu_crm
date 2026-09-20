import { useState, type FormEvent } from "react";
import { Plus } from "lucide-react";

/** Trailing "+ Добавить колонку" action at the end of a board — a personal, non-system column with a
 * plain non-empty Unicode title. */
export function AddBoardColumn({ onAdd }: { onAdd: (title: string) => void }) {
  const [adding, setAdding] = useState(false);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const title = String(new FormData(e.currentTarget).get("title") ?? "").trim();
    if (title) onAdd(title);
    setAdding(false);
  }

  if (!adding) {
    return (
      <button type="button" className="secondary add-board-column" onClick={() => setAdding(true)}>
        <Plus size={15} /> Добавить колонку
      </button>
    );
  }

  return (
    <form className="add-board-column-form" onSubmit={submit}>
      <input name="title" placeholder="Название колонки" maxLength={60} autoFocus aria-label="Название новой колонки" />
      <div className="add-board-column-form-actions">
        <button type="button" className="text-button" onClick={() => setAdding(false)}>
          Отмена
        </button>
        <button type="submit" className="secondary">
          Добавить
        </button>
      </div>
    </form>
  );
}
