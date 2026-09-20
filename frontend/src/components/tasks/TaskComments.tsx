import { useId, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { errorText } from "../../api/client";
import { formatFileSize } from "../../api/imports";
import { ATTACHMENT_ACCEPT, ATTACHMENT_FORMATS_TEXT, MAX_ATTACHMENTS, addAttachments } from "../../api/workflows";
import { useAddComment, useComments, type TaskComment } from "../../api/tasks";
import { formatDateTime } from "../../lib/format";

function CommentRow({ comment }: { comment: TaskComment }) {
  return (
    <li className="comment">
      <div className="comment-head">
        <strong>{comment.author?.full_name ?? "Система"}</strong>
        <time>{formatDateTime(comment.created_at)}</time>
      </div>
      {comment.body && <p>{comment.body}</p>}
      {comment.attachments.length > 0 && (
        <ul className="file-list">
          {comment.attachments.map((a) => (
            <li key={a.id}>
              <a href={`/api/v1/attachments/${a.id}`}>{a.filename}</a>
              <small>{formatFileSize(a.size_bytes)}</small>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function TaskComments({ taskId }: { taskId: number }) {
  const id = useId();
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileErrors, setFileErrors] = useState<string[]>([]);
  const comments = useComments(taskId);
  const add = useAddComment(taskId);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!body.trim() && !files.length) return;
    add.mutate({ body: body.trim(), files }, { onSuccess: () => { setBody(""); setFiles([]); setFileErrors([]); } });
  }

  return (
    <div className="task-comments">
      <h3>Комментарии</h3>
      <ul className="comment-list">
        {comments.data?.map((c) => (
          <CommentRow comment={c} key={c.id} />
        ))}
        {comments.data && !comments.data.length && <p className="empty">Комментариев пока нет.</p>}
      </ul>
      <form onSubmit={submit}>
        <label>
          <span className="visually-hidden">Новый комментарий</span>
          <textarea
            rows={2}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Написать комментарий…"
            aria-describedby={`${id}-hint`}
          />
        </label>
        <div className="file-picker">
          <label className="secondary file-button">
            Прикрепить файлы
            <input
              type="file"
              multiple
              className="visually-hidden"
              accept={ATTACHMENT_ACCEPT}
              onChange={(e) => {
                const chosen = Array.from(e.target.files ?? []);
                e.target.value = "";
                const result = addAttachments(files, chosen);
                setFiles(result.files);
                setFileErrors(result.errors);
              }}
            />
          </label>
          <small id={`${id}-hint`} className="field-hint">
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
                    onClick={() => setFiles(files.filter((_, j) => j !== i))}
                  >
                    <X size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {fileErrors.length > 0 && (
            <ul className="field-errors danger">
              {fileErrors.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
        </div>
        {add.isError && <p className="danger" role="alert">{errorText(add.error)}</p>}
        <div className="modal-actions">
          <button className="primary" disabled={add.isPending || (!body.trim() && !files.length)}>
            {add.isPending ? "Отправляем…" : "Отправить"}
          </button>
        </div>
      </form>
    </div>
  );
}
