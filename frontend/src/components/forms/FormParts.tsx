import { ApiError, errorText } from "../../api/client";

/** Server-reported message for one form field (from ApiError.details). */
export function FieldError({
  error,
  field,
}: {
  error: unknown;
  field: string;
}) {
  const message = fieldErrorMessage(error, field);
  return message ? (
    <small className="field-error danger">{message}</small>
  ) : null;
}

/**
 * Message the server reported for a field or its items ("contact_ids.0").
 * A detail without its own text falls back to the error message (e.g. CONFLICT).
 */
export function fieldErrorMessage(error: unknown, field: string): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  const detail = error.details?.find(
    (d) => d.field === field || d.field?.startsWith(`${field}.`),
  );
  return detail ? detail.message || error.message : undefined;
}

export function FormFooter({
  error,
  pending,
  onCancel,
  submitLabel = "Создать",
}: {
  error: unknown;
  pending: boolean;
  onCancel: () => void;
  submitLabel?: string;
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
          {pending ? "Сохраняем…" : submitLabel}
        </button>
      </div>
    </>
  );
}

export const formText = (form: FormData, name: string) =>
  String(form.get(name) ?? "");
