import { useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Pencil, Trash2 } from "lucide-react";
import { Modal } from "../Modal";

/**
 * Shared column-header chrome for both boards (planner, Deadlines): move-left/right (keyboard-operable
 * buttons — the reliable alternative to column drag, matching this app's established pattern of pairing
 * a drag interaction with explicit buttons), and for a custom column only, rename (inline) and delete
 * (with a confirmation dialog, since it's irreversible for the column itself even though its tasks are
 * never touched).
 */
export function BoardColumnHeader({
  label,
  count,
  isCustom,
  canMoveLeft,
  canMoveRight,
  onMoveLeft,
  onMoveRight,
  onRename,
  onDelete,
}: {
  label: string;
  count: number;
  isCustom: boolean;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  onMoveLeft: () => void;
  onMoveRight: () => void;
  onRename?: (title: string) => void;
  onDelete?: () => void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  function submitRename(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const title = String(new FormData(e.currentTarget).get("title") ?? "").trim();
    if (title) onRename?.(title);
    setRenaming(false);
  }

  return (
    <div className="board-column-head">
      <div className="board-column-head-row">
        <button type="button" className="icon-button" aria-label={`Сдвинуть колонку «${label}» левее`} disabled={!canMoveLeft} onClick={onMoveLeft}>
          <ArrowLeft size={13} />
        </button>
        {renaming ? (
          <form className="board-column-rename" onSubmit={submitRename}>
            <input name="title" defaultValue={label} maxLength={60} autoFocus aria-label={`Название колонки «${label}»`} />
            <button type="submit" className="text-button">
              ОК
            </button>
          </form>
        ) : (
          <h3>{label}</h3>
        )}
        <button type="button" className="icon-button" aria-label={`Сдвинуть колонку «${label}» правее`} disabled={!canMoveRight} onClick={onMoveRight}>
          <ArrowRight size={13} />
        </button>
      </div>
      <div className="board-column-head-row">
        <span className="muted">{count}</span>
        {isCustom && (
          <span className="board-column-actions">
            <button type="button" className="icon-button" aria-label={`Переименовать колонку «${label}»`} onClick={() => setRenaming(true)}>
              <Pencil size={13} />
            </button>
            <button type="button" className="icon-button" aria-label={`Удалить колонку «${label}»`} onClick={() => setConfirmingDelete(true)}>
              <Trash2 size={13} />
            </button>
          </span>
        )}
      </div>
      {confirmingDelete && (
        <Modal title={`Удалить колонку «${label}»?`} close={() => setConfirmingDelete(false)}>
          <p>Колонка будет удалена без возможности восстановления. Задачи не удаляются — каждая вернётся в свою обычную колонку.</p>
          <div className="modal-actions">
            <button type="button" className="secondary" onClick={() => setConfirmingDelete(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => {
                setConfirmingDelete(false);
                onDelete?.();
              }}
            >
              Удалить
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
