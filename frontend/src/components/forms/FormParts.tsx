import { ApiError, errorText } from "../../api/client";

/** Server-reported message for one form field (from ApiError.details). */
export function FieldError({
  error,
  field,
}: {
  error: unknown;
  field: string;
}) {
  const message =
    error instanceof ApiError ? error.fieldMessage(field) : undefined;
  return message ? (
    <small className="field-error danger">{message}</small>
  ) : null;
}

export function FormFooter({
  error,
  pending,
  onCancel,
}: {
  error: unknown;
  pending: boolean;
  onCancel: () => void;
}) {
  return (
    <>
      {error ? (
        <p className="danger" role="alert">
          {errorText(error)}
        </p>
      ) : null}
      <div className="modal-actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Отмена
        </button>
        <button className="primary" disabled={pending}>
          {pending ? "Сохраняем…" : "Создать"}
        </button>
      </div>
    </>
  );
}

export const formText = (form: FormData, name: string) =>
  String(form.get(name) ?? "");
