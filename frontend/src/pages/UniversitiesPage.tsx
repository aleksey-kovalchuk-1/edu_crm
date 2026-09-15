import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ArrowUpRight, Building2, ExternalLink, Pencil } from "lucide-react";
import { useUniversities } from "../api/catalogs";
import { useLaunches } from "../api/queries";
import type { University } from "../api/types";
import { useSession } from "../app/AuthGate";
import { paths, universityPath } from "../app/navigation";
import { Modal } from "../components/Modal";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import { UniversityForm } from "../components/forms/UniversityForm";
import { safeWebsiteUrl } from "../lib/format";
import { canEditCatalog } from "../lib/user";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import type { InteractionsState } from "./InteractionsPage";

export const NO_UNIVERSITIES_TEXT =
  "Вам пока не назначены учебные заведения. Обратитесь к руководителю.";

export function WebsiteLink({ website }: { website: string }) {
  const href = safeWebsiteUrl(website);
  if (!href) return website ? <span>{website}</span> : null;
  return (
    <a className="website-link" href={href} target="_blank" rel="noopener noreferrer">
      {website.replace(/^https?:\/\//i, "").replace(/\/$/, "")}
      <ExternalLink size={12} aria-hidden="true" />
      <span className="visually-hidden"> (откроется в новой вкладке)</span>
    </a>
  );
}

export const placeLabel = (u: University) =>
  [u.city, u.region].filter(Boolean).join(", ");

export function UniversitiesPage() {
  const navigate = useNavigate();
  const { user } = useSession();
  const canEdit = canEditCatalog(user.roles);
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const q = useDebouncedValue(search);
  const [editing, setEditing] = useState<University | null>(null);
  const universities = useUniversities({ q, include_inactive: showInactive });
  const launches = useLaunches();
  const queries = [universities, launches];
  const fallback = queryFallback(queries);
  const universityList = universities.data;
  const launchList = launches.data;
  if (fallback || !universityList || !launchList) return fallback;

  const unassigned = !canEdit && !universityList.length && !q.trim() && !showInactive;

  return (
    <>
      <RefreshError queries={queries} />
      <SearchToolbar
        search={search}
        onSearch={setSearch}
        count={universityList.length}
        placeholder="Поиск по названию или городу"
      >
        <label className="toggle">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Показать неактивные
        </label>
      </SearchToolbar>
      {unassigned ? (
        <p className="empty panel empty-state">{NO_UNIVERSITIES_TEXT}</p>
      ) : (
        <div className="university-grid">
          {universityList.map((u) => (
            <article className="panel university-card" key={u.id}>
              <div className="university-card-top">
                <div className="university-icon">
                  <Building2 size={25} />
                </div>
                {canEdit && (
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Изменить ${u.name}`}
                    title="Изменить"
                    onClick={() => setEditing(u)}
                  >
                    <Pencil size={16} />
                  </button>
                )}
              </div>
              <span className="muted">
                {placeLabel(u)}
                {!u.is_active && <span className="badge badge-4 inline-badge">Неактивно</span>}
              </span>
              <h2>
                <Link className="card-title-link" to={universityPath(u.id)}>
                  {u.short_name && <span className="short-name">{u.short_name}</span>}
                  {u.name}
                </Link>
              </h2>
              {u.website && (
                <p>
                  <WebsiteLink website={u.website} />
                </p>
              )}
              <p>
                Ответственные:{" "}
                {u.managers.length
                  ? u.managers.map((m) => m.full_name).join(", ")
                  : "не назначены"}
              </p>
              <div className="university-bottom">
                <span>
                  {launchList.filter((l) => l.university_id === u.id).length} программ
                </span>
                <button
                  type="button"
                  className="text-button"
                  onClick={() =>
                    navigate(paths.interactions, {
                      state: { search: u.name } satisfies InteractionsState,
                    })
                  }
                >
                  Открыть взаимодействия <ArrowUpRight size={16} />
                </button>
              </div>
            </article>
          ))}
          {!universityList.length && <p className="empty">Учебные заведения не найдены.</p>}
        </div>
      )}
      {editing && (
        <Modal title="Изменить учебное заведение" close={() => setEditing(null)}>
          <UniversityForm university={editing} onDone={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}
