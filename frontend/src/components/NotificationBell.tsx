import { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { Link } from "react-router";
import { errorText } from "../api/client";
import { useMarkAllRead, useMarkRead, useNotifications, useUnreadCount, type NotificationItem } from "../api/notifications";
import { formatDateTime } from "../lib/format";

/** Top-right bell on every page: neutral with nothing unread, highlighted with a count otherwise. */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const count = useUnreadCount().data?.count ?? 0;
  const list = useNotifications(open);
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  function openItem(item: NotificationItem) {
    if (!item.read_at) markRead.mutate(item.id);
    setOpen(false);
  }

  return (
    <div className="notification-bell" ref={box}>
      <button
        type="button"
        className={count > 0 ? "icon-button bell-button has-unread" : "icon-button bell-button"}
        aria-label={count > 0 ? `Уведомления: ${count} непрочитанных` : "Уведомления"}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen(!open)}
      >
        <Bell size={19} aria-hidden="true" />
        {count > 0 && <span className="bell-count" data-testid="unread-count">{count > 99 ? "99+" : count}</span>}
      </button>
      {open && (
        <section className="notification-panel" aria-label="Список уведомлений">
          <header>
            <strong>Уведомления</strong>
            {count > 0 && (
              <button type="button" className="link-button" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
                Отметить все прочитанными
              </button>
            )}
          </header>
          {list.isPending && <p className="muted">Загрузка…</p>}
          {list.isError && <p className="danger" role="alert">{errorText(list.error)}</p>}
          {list.data?.length === 0 && <p className="muted">Новых уведомлений нет</p>}
          <ul>
            {list.data?.map((item) => {
              const content = (
                <>
                  <span className="notification-title">{item.title}</span>
                  <span className="notification-body">{item.body}</span>
                  <time className="muted" dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                </>
              );
              return (
                <li key={item.id} className={item.read_at ? "notification-item" : "notification-item unread"}>
                  {item.link ? (
                    <Link to={item.link.path} onClick={() => openItem(item)}>{content}</Link>
                  ) : (
                    <button type="button" className="notification-plain" onClick={() => !item.read_at && markRead.mutate(item.id)}>
                      {content}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
