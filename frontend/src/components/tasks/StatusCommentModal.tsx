import type { FormEvent } from "react";
import { Modal } from "../Modal";
import { FormFooter } from "../forms/FormParts";

/** The one status transition ("Вернуть на доработку") that requires a reason — shared by the quick
 * status buttons and the "Мой план" board (drag or its keyboard alternative), so the same required-comment
 * rule always shows the same form. */
export function StatusCommentModal({
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  pending: boolean;
  error: unknown;
  onCancel: () => void;
  onSubmit: (comment: string) => void;
}) {
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    onSubmit(String(new FormData(e.currentTarget).get("comment") ?? ""));
  }
  return (
    <Modal title="Вернуть на доработку" close={onCancel}>
      <form onSubmit={submit}>
        <label>
          Что нужно исправить
          <textarea name="comment" required maxLength={2000} rows={3} autoFocus />
        </label>
        <FormFooter error={error} pending={pending} onCancel={onCancel} submitLabel="Вернуть" />
      </form>
    </Modal>
  );
}
