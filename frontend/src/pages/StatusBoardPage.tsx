import { useState } from "react";
import { Link } from "react-router";
import { ArrowLeft, CalendarDays, Users } from "lucide-react";
import { useLaunches } from "../api/queries";
import { defaultWorkflow, groupByStatus, useWorkflows } from "../api/workflows";
import { launchPath, paths } from "../app/navigation";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import { formatDate, initials, launchCode, matches } from "../lib/format";

/** Launches grouped by the statuses of the default workflow; cards open the detail. */
export function StatusBoardPage() {
  const [search, setSearch] = useState("");
  const launches = useLaunches();
  const workflows = useWorkflows();
  const queries = [launches, workflows];
  const fallback = queryFallback(queries);
  if (fallback || !launches.data || !workflows.data) return fallback;

  const workflow = defaultWorkflow(workflows.data);
  if (!workflow) return <div className="empty">Базовый процесс не настроен.</div>;
  const filtered = launches.data.filter((l) =>
    matches(`${l.program} ${l.university} ${l.city} ${l.owner}`, search),
  );
  const columns = groupByStatus(workflow, filtered);

  return (
    <>
      <RefreshError queries={queries} />
      <div className="detail-links">
        <Link className="back-link text-button" to={paths.interactions}>
          <ArrowLeft size={16} />
          Доска этапов
        </Link>
        <span className="muted-text">Процесс: {workflow.name}</span>
      </div>
      <SearchToolbar search={search} onSearch={setSearch} count={filtered.length} />
      <div className="status-board">
        {columns.map((column) => {
          const titleId = `board-${column.key}`;
          return (
            <section className="board-column" key={column.key} aria-labelledby={titleId}>
              <div className="column-title">
                <i className="dot purple" aria-hidden="true" />
                <h2 id={titleId}>{column.title}</h2>
                {column.status && !column.status.is_active && <small className="muted">отключён</small>}
                <span aria-label={`Взаимодействий: ${column.launches.length}`}>{column.launches.length}</span>
              </div>
              {column.launches.length ? (
                <ul className="board-cards">
                  {column.launches.map((l) => (
                    <li key={l.id}>
                      <Link className="launch-card" to={launchPath(l.id)}>
                        <span className="card-id">{launchCode(l.id)}</span>
                        <h3>{l.program}</h3>
                        <p>{l.university}</p>
                        <div className="card-meta">
                          <span>
                            <Users size={14} aria-hidden="true" />
                            {l.students}
                          </span>
                          <span className={l.overdue ? "danger" : ""}>
                            <CalendarDays size={14} aria-hidden="true" />
                            {formatDate(l.deadline)}
                          </span>
                        </div>
                        <div className="card-owner">
                          <span className="avatar tiny" aria-hidden="true">
                            {initials(l.owner)}
                          </span>
                          {l.owner}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="column-empty">Нет взаимодействий</div>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
