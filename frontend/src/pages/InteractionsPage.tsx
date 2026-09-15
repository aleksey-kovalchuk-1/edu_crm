import { useState } from "react";
import { useLocation } from "react-router";
import { ArrowUpRight, CalendarDays, Clock3, Users } from "lucide-react";
import { useLaunches, useStages } from "../api/queries";
import { useOpenLaunch } from "../app/LaunchDetail";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import {
  formatDate,
  initials,
  launchCode,
  matches,
  stageGroup,
  stageGroups,
} from "../lib/format";

/** Navigation state accepted by this page (e.g. from a university card). */
export interface InteractionsState {
  search?: string;
}

export function InteractionsPage() {
  const location = useLocation();
  const openLaunch = useOpenLaunch();
  const [search, setSearch] = useState(
    () => (location.state as InteractionsState | null)?.search ?? "",
  );
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  const launches = useLaunches();
  const stages = useStages();
  const queries = [launches, stages];
  const fallback = queryFallback(queries);
  const launchList = launches.data;
  const stageNames = stages.data;
  if (fallback || !launchList || !stageNames) return fallback;

  const filtered = launchList.filter(
    (l) =>
      matches(`${l.program} ${l.university} ${l.city} ${l.owner}`, search) &&
      (!onlyOverdue || l.overdue),
  );
  return (
    <>
      <RefreshError queries={queries} />
      <SearchToolbar
        search={search}
        onSearch={setSearch}
        count={filtered.length}
      >
        <button
          className={onlyOverdue ? "filter selected" : "filter"}
          onClick={() => setOnlyOverdue(!onlyOverdue)}
        >
          <Clock3 size={16} />
          Требуют внимания
        </button>
      </SearchToolbar>
      <div className="board">
        {stageGroups.map((g, i) => {
          const column = filtered.filter((l) => stageGroup(l.stage) === i);
          return (
            <section className="board-column" key={g}>
              <div className="column-title">
                <i className={`dot group-${i}`} />
                <h2>{g}</h2>
                <span>{column.length}</span>
              </div>
              {column.map((l) => (
                <button
                  className="launch-card"
                  key={l.id}
                  onClick={() => openLaunch(l.id)}
                >
                  <span className="card-id">
                    {launchCode(l.id)} <ArrowUpRight size={14} />
                  </span>
                  <h3>{l.program}</h3>
                  <p>{l.university}</p>
                  <span className={`badge badge-${i}`}>
                    {stageNames[l.stage]}
                  </span>
                  <div className="card-meta">
                    <span>
                      <Users size={14} />
                      {l.students}
                    </span>
                    <span className={l.overdue ? "danger" : ""}>
                      <CalendarDays size={14} />
                      {formatDate(l.deadline)}
                    </span>
                  </div>
                  <div className="card-owner">
                    <span className="avatar tiny">{initials(l.owner)}</span>
                    {l.owner}
                  </div>
                </button>
              ))}
              {!column.length && (
                <div className="column-empty">Нет взаимодействий</div>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
