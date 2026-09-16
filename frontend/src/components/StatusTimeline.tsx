import { Paperclip } from "lucide-react";
import { formatFileSize } from "../api/imports";
import { attachmentUrl, type StatusChange } from "../api/workflows";
import { formatDateTime } from "../lib/format";

function changeTitle(change: StatusChange) {
  if (!change.from_status) return `Создано в статусе «${change.to_status.name}»`;
  if (change.from_status.id === change.to_status.id) return `Дополнение к статусу «${change.to_status.name}»`;
  return `«${change.from_status.name}» → «${change.to_status.name}»`;
}

/** Status changes newest first, with comments, authors and attachment links. */
export function StatusTimeline({ changes }: { changes: StatusChange[] }) {
  if (!changes.length) return <p className="empty">История пока пуста.</p>;
  return (
    <ol className="timeline" aria-label="История статусов">
      {changes.map((c) => (
        <li className="timeline-item" key={c.id}>
          <i className="dot purple" aria-hidden="true" />
          <div className="timeline-body">
            <div className="timeline-head">
              <strong>{changeTitle(c)}</strong>
              <time dateTime={c.created_at}>{formatDateTime(c.created_at)}</time>
            </div>
            <small className="timeline-author">{c.author?.full_name ?? "Системная запись"}</small>
            {c.comment && <p className="timeline-comment">{c.comment}</p>}
            {c.attachments.length > 0 && (
              <ul className="attachment-list" aria-label="Файлы">
                {c.attachments.map((a) => (
                  <li key={a.id}>
                    <a href={attachmentUrl(a.id)} download={a.filename}>
                      <Paperclip size={14} aria-hidden="true" />
                      {a.filename}
                    </a>
                    <small>{formatFileSize(a.size_bytes)}</small>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
