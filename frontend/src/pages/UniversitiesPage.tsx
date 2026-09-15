import { useState } from "react";
import { useNavigate } from "react-router";
import { ArrowUpRight, Building2 } from "lucide-react";
import { useLaunches, useUniversities } from "../api/queries";
import { paths } from "../app/navigation";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import { matches } from "../lib/format";
import type { InteractionsState } from "./InteractionsPage";

export function UniversitiesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const universities = useUniversities();
  const launches = useLaunches();
  const queries = [universities, launches];
  const fallback = queryFallback(queries);
  const universityList = universities.data;
  const launchList = launches.data;
  if (fallback || !universityList || !launchList) return fallback;

  const filtered = universityList.filter((u) =>
    matches(`${u.name} ${u.city} ${u.contact}`, search),
  );
  return (
    <>
      <RefreshError queries={queries} />
      <SearchToolbar
        search={search}
        onSearch={setSearch}
        count={filtered.length}
      />
      <div className="university-grid">
        {filtered.map((u) => (
          <article className="panel university-card" key={u.id}>
            <div className="university-icon">
              <Building2 size={25} />
            </div>
            <span className="muted">{u.city}</span>
            <h2>{u.name}</h2>
            <p>Контакт: {u.contact || "Не указан"}</p>
            <div className="university-bottom">
              <span>
                {launchList.filter((l) => l.university_id === u.id).length}{" "}
                программ
              </span>
              <button
                className="text-button"
                onClick={() =>
                  navigate(paths.interactions, {
                    state: { search: u.name } satisfies InteractionsState,
                  })
                }
              >
                Открыть <ArrowUpRight size={16} />
              </button>
            </div>
          </article>
        ))}
        {!filtered.length && (
          <p className="empty">Учебные заведения не найдены.</p>
        )}
      </div>
    </>
  );
}
