import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { useRecentActions } from "../api/queries";
import { useSession } from "../app/AuthGate";
import { formatDateTime, formatRelativeTime } from "../lib/format";
import { seesAllActions } from "../lib/user";
import { queryFallback } from "./QueryState";

const LIMIT = 10;

/** Current time, refreshed every minute so relative times stay correct. */
function useNow(intervalMs = 60_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export function RecentActions() {
  const { user } = useSession();
  const actions = useRecentActions(LIMIT);
  const now = useNow();
  // A crm-user only sees their own actions, so the name would always be theirs.
  const showUser = seesAllActions(user.roles);
  const fallback = queryFallback([actions]);
  const events = actions.data;

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>Последние действия</h2>
          <p>{showUser ? "Изменения всех сотрудников" : "Ваши изменения"}</p>
        </div>
        <History size={20} className="muted" aria-hidden="true" />
      </div>
      {fallback ??
        (events && events.length ? (
          <ul className="activity-list">
            {events.map((e) => (
              <li className="activity" key={e.id}>
                <i className="dot purple" aria-hidden="true" />
                <div>
                  <strong>{e.summary}</strong>
                  {showUser && <small>{e.user?.full_name ?? "Система"}</small>}
                </div>
                <time dateTime={e.occurred_at} title={formatDateTime(e.occurred_at)}>
                  {formatRelativeTime(e.occurred_at, now)}
                </time>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">Действий пока нет.</p>
        ))}
    </section>
  );
}
