import { useId, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { errorText } from "../api/client";
import { formatFileSize } from "../api/imports";
import type { Launch } from "../api/types";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_FORMATS_TEXT,
  MAX_ATTACHMENTS,
  MAX_COMMENT_LENGTH,
  addAttachments,
  sortedStatuses,
  useChangeStatus,
  type Workflow,
} from "../api/workflows";
import { Modal } from "./Modal";
import { fieldErrorMessage } from "./forms/FormParts";

export const SAME_STATUS_MESSAGE = "Взаимодействие уже в этом статусе: добавьте комментарий или файл";

export function StatusChangeDialog({
  launch,
  workflow,
  currentStatusId,
  close,
}: {
  launch: Launch;
  workflow: Workflow;
  currentStatusId: number | undefined;
  close: () => void;
}) {
  const active = sortedStatuses(workflow).filter((s) => s.is_active);
  const [statusId, setStatusId] = useState<number>(
    active.some((s) => s.id === currentStatusId) ? currentStatusId! : (active[0]?.id ?? 0),
  );
  const [comment, setComment] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileErrors, setFileErrors] = useState<string[]>([]);
  const [statusError, setStatusError] = useState<string | null>(null);
  const change = useChangeStatus(launch.id);
  const id = useId();

  const tooLong = comment.length > MAX_COMMENT_LENGTH;
  const statusMessage = statusError ?? fieldErrorMessage(change.error, "status_id");
  const commentMessage = tooLong
    ? `Комментарий длиннее ${MAX_COMMENT_LENGTH} символов: сократите его на ${comment.length - MAX_COMMENT_LENGTH}.`
    : fieldErrorMessage(change.error, "comment");
  const serverFilesMessage = fieldErrorMessage(change.error, "files");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (tooLong) return;
    if (statusId === currentStatusId && !comment.trim() && !files.length) {
      setStatusError(SAME_STATUS_MESSAGE);
      return;
    }
    change.mutate({ status_id: statusId, comment, files }, { onSuccess: close });
  };

  return (
    <Modal title="Сменить статус" close={close}>
      <form onSubmit={submit} noValidate>
        <p className="form-note">
          {launch.program} · {launch.university}
        </p>
        <label>
          Статус
          <select
            name="status_id"
            value={statusId}
            aria-invalid={statusMessage ? true : undefined}
            onChange={(e) => {
              setStatusId(Number(e.target.value));
              setStatusError(null);
            }}
          >
            {active.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.id === currentStatusId ? " (текущий)" : ""}
              </option>
            ))}
          </select>
          {statusMessage && <small className="field-error danger">{statusMessage}</small>}
        </label>
        <label>
          Комментарий
          <textarea
            name="comment"
            rows={4}
            value={comment}
            aria-describedby={`${id}-counter`}
            aria-invalid={commentMessage ? true : undefined}
            onChange={(e) => {
              setComment(e.target.value);
              setStatusError(null);
            }}
          />
          <small id={`${id}-counter`} className={tooLong ? "char-counter danger" : "char-counter"}>
            {comment.length} / {MAX_COMMENT_LENGTH}
          </small>
          {commentMessage && <small className="field-error danger">{commentMessage}</small>}
        </label>
        <div className="file-picker">
          <label className="secondary file-button">
            Прикрепить файлы
            <input
              type="file"
              multiple
              className="visually-hidden"
              accept={ATTACHMENT_ACCEPT}
              aria-describedby={`${id}-files-hint`}
              onChange={(e) => {
                const chosen = Array.from(e.target.files ?? []);
                e.target.value = "";
                const result = addAttachments(files, chosen);
                setFiles(result.files);
                setFileErrors(result.errors);
                setStatusError(null);
              }}
            />
          </label>
          <small id={`${id}-files-hint`} className="field-hint">
            До {MAX_ATTACHMENTS} файлов по 20 МБ: {ATTACHMENT_FORMATS_TEXT}.
          </small>
          {files.length > 0 && (
            <ul className="file-list" aria-label="Выбранные файлы">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`}>
                  <span>{f.name}</span>
                  <small>{formatFileSize(f.size)}</small>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Убрать файл «${f.name}»`}
                    onClick={() => {
                      setFiles(files.filter((_, j) => j !== i));
                      setFileErrors([]);
                    }}
                  >
                    <X size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {(fileErrors.length > 0 || serverFilesMessage) && (
            <ul className="field-errors danger" data-testid="file-errors">
              {fileErrors.map((m) => (
                <li key={m}>{m}</li>
              ))}
              {serverFilesMessage && <li>{serverFilesMessage}</li>}
            </ul>
          )}
        </div>
        {change.error && (
          <p className="danger" role="alert">
            {errorText(change.error)}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={close}>
            Отмена
          </button>
          <button className="primary" disabled={change.isPending || !active.length}>
            {change.isPending ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
