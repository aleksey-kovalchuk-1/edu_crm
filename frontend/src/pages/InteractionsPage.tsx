import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import {
  ArrowUpRight,
  CalendarDays,
  Clock3,
  Columns3,
  Users,
} from "lucide-react";
import { useItProducts } from "../api/catalogs";
import { useLaunches, useStages } from "../api/queries";
import type { Launch } from "../api/types";
import { useWorkflows } from "../api/workflows";
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

/** URL parameters of the register filters, so a filtered view can be linked (requirement: filter by university,
 * IT programme, IT product and status). Each is one value; empty means «all». */
const FILTERS = ["university", "program", "product", "status"] as const;
type FilterKey = (typeof FILTERS)[number];

function keep(launch: Launch, filters: Record<FilterKey, string>) {
  return (
    (!filters.university || String(launch.university_id) === filters.university) &&
    (!filters.program || launch.program === filters.program) &&
    (!filters.product || String(launch.it_product_id ?? "") === filters.product) &&
    (!filters.status || String(launch.status_id ?? "") === filters.status)
  );
}

const byLabel = (a: [string, string], b: [string, string]) => a[1].localeCompare(b[1], "ru");

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
  const workflows = useWorkflows();
  const products = useItProducts();
  const filters = Object.fromEntries(FILTERS.map((key) => [key, params.get(key) ?? ""])) as Record<FilterKey, string>;
  const anyFilter = FILTERS.some((key) => filters[key]);
  const setFilter = (key: FilterKey | null, value = "") =>
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        for (const k of key ? [key] : FILTERS) {
          if (key && value) updated.set(k, value);
          else updated.delete(k);
        }
        return updated;
      },
      { replace: true },
    );
  const queries = [launches, stages];
  const fallback = queryFallback(queries);
  const launchList = launches.data;
  const stageNames = stages.data;
  if (fallback || !launchList || !stageNames) return fallback;

  // Options come from the interactions this user can see, so every choice leads somewhere.
  const statusNames = new Map((workflows.data ?? []).flatMap((w) => w.statuses.map((st) => [String(st.id), st.name] as const)));
  const productNames = new Map((products.data ?? []).map((p) => [String(p.id), `${p.vendor} — ${p.name}`] as const));
  const universityOptions = [...new Map(launchList.map((l) => [String(l.university_id), l.university])).entries()].sort(byLabel);
  const programOptions = [...new Set(launchList.map((l) => l.program))].sort((a, b) => a.localeCompare(b, "ru"));
  const productOptions = [...new Set(launchList.map((l) => l.it_product_id).filter((id): id is number => id != null))]
    .map((id) => [String(id), productNames.get(String(id)) ?? `Продукт №${id}`] as [string, string])
    .sort(byLabel);
  const statusOptions = [...new Set(launchList.map((l) => l.status_id).filter((id): id is number => id != null))]
    .map((id) => [String(id), statusNames.get(String(id)) ?? `Статус №${id}`] as [string, string]);
  const statusOrder = (workflows.data ?? []).flatMap((w) => w.statuses.map((st) => String(st.id)));
  statusOptions.sort((a, b) => statusOrder.indexOf(a[0]) - statusOrder.indexOf(b[0]));

  const filtered = launchList.filter(
    (l) =>
      matches(`${l.program} ${l.product} ${l.university} ${l.city} ${l.owner}`, search) &&
      (!onlyOverdue || l.overdue) &&
      keep(l, filters),
  );
  const select = (key: FilterKey, label: string, all: string, options: [string, string][]) => (
    <label className="register-filter">
      <span className="visually-hidden">{label}</span>
      <select aria-label={label} value={filters[key]} onChange={(e) => setFilter(key, e.target.value)}>
        <option value="">{all}</option>
        {options.map(([value, text]) => (
          <option value={value} key={value}>
            {text}
          </option>
        ))}
      </select>
    </label>
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
      <div className="register-filters" role="group" aria-label="Фильтры взаимодействий">
        {select("university", "Вуз", "Все вузы", universityOptions)}
        {select("program", "ИТ-программа", "Все программы", programOptions.map((p) => [p, p]))}
        {select("product", "ИТ-продукт", "Все продукты", productOptions)}
        {select("status", "Статус", "Все статусы", statusOptions)}
        {anyFilter && (
          <button type="button" className="text-button" onClick={() => setFilter(null)}>
            Сбросить фильтры
          </button>
        )}
      </div>
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
