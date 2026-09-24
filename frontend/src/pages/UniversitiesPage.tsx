import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ArrowUpRight, ExternalLink, Pencil } from "lucide-react";
import { useUniversities } from "../api/catalogs";
import { useLaunches } from "../api/queries";
import type { University } from "../api/types";
import { useSession } from "../app/AuthGate";
import { paths, universityPath } from "../app/navigation";
import { Modal } from "../components/Modal";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import { UniversityForm } from "../components/forms/UniversityForm";
import { PersonAvatars } from "../components/tasks/PersonAvatars";
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
        <div className="panel table-wrap university-table">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Название</th>
                <th scope="col">Город, регион</th>
                <th scope="col">Ответственные</th>
                <th scope="col">Программ</th>
                <th scope="col">
                  <span className="visually-hidden">Действия</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {universityList.map((u) => (
                <tr key={u.id}>
                  <td className="university-name-cell">
                    <Link className="cell-title" to={universityPath(u.id)}>
                      {u.short_name && <span className="short-name">{u.short_name}</span>}
                      <span>{u.name}</span>
                    </Link>
                    {!u.is_active && <span className="badge badge-4 inline-badge">Неактивно</span>}
                    {u.website && (
                      <div className="university-site">
                        <WebsiteLink website={u.website} />
                      </div>
                    )}
                  </td>
                  <td>{placeLabel(u) || <span className="muted">—</span>}</td>
                  <td>
                    <PersonAvatars people={u.managers} />
                  </td>
                  <td>{launchList.filter((l) => l.university_id === u.id).length}</td>
                  <td className="row-actions">
                    <button
                      type="button"
                      className="text-button"
                      aria-label={`Взаимодействия: ${u.name}`}
                      onClick={() =>
                        navigate(paths.interactions, {
                          state: { search: u.name } satisfies InteractionsState,
                        })
                      }
                    >
                      Взаимодействия <ArrowUpRight size={14} />
                    </button>
                    {canEdit && (
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Изменить ${u.name}`}
                        title="Изменить"
                        onClick={() => setEditing(u)}
                      >
                        <Pencil size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
