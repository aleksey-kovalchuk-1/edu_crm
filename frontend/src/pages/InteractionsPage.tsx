import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import {
  ArrowUpRight,
  CalendarDays,
  Clock3,
  Columns3,
  Users,
} from "lucide-react";
import { useLaunches, useStages } from "../api/queries";
import { launchPath, paths } from "../app/navigation";
import { LaunchTable } from "../components/LaunchTable";
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
  const [search, setSearch] = useState(
    () => (location.state as InteractionsState | null)?.search ?? "",
  );
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  // «Реестр» (a table) is the default; «Этапы» (cards grouped by stage) is kept in the URL so it can be linked.
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "stages" ? "stages" : "register";
  const showView = (next: "register" | "stages") =>
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        if (next === "stages") updated.set("view", "stages");
        else updated.delete("view");
        return updated;
      },
      { replace: true },
    );
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
        <div className="segmented" role="group" aria-label="Вид">
          <button
            type="button"
            aria-pressed={view === "register"}
            onClick={() => showView("register")}
          >
            Реестр
          </button>
          <button
            type="button"
            aria-pressed={view === "stages"}
            onClick={() => showView("stages")}
          >
            Этапы
          </button>
        </div>
        <button
          className={onlyOverdue ? "filter selected" : "filter"}
          onClick={() => setOnlyOverdue(!onlyOverdue)}
        >
          <Clock3 size={16} />
          Требуют внимания
        </button>
        <Link className="filter" to={paths.statusBoard}>
          <Columns3 size={16} />
          Доска статусов
        </Link>
      </SearchToolbar>
      {view === "register" ? (
        <div className="panel">
          <LaunchTable rows={filtered} stages={stageNames} />
        </div>
      ) : (
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
                  <Link
                    className="launch-card"
                    key={l.id}
                    to={launchPath(l.id)}
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
                  </Link>
                ))}
                {!column.length && (
                  <div className="column-empty">Нет взаимодействий</div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
