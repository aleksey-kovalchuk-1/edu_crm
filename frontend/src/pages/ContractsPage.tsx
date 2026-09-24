import { useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { Filter, X } from "lucide-react";
import {
  useCrmUsers,
  useItDirections,
  useItProducts,
  useTransferStatuses,
  useUniversities,
} from "../api/catalogs";
import type { ContractFilters } from "../api/types";
import { useSession } from "../app/AuthGate";
import { ContractsTable } from "../components/ContractsTable";
import { SearchToolbar } from "../components/SearchToolbar";
import { ROLES, canEditCatalog } from "../lib/user";
import { NO_UNIVERSITIES_TEXT } from "./UniversitiesPage";

/** URL query parameters of this page (same names as the API filters). */
const FILTER_KEYS = [
  "q",
  "university_id",
  "it_direction_id",
  "it_product_id",
  "manager_user_id",
  "transfer_status",
  "signed_from",
  "signed_to",
] as const;
type FilterKey = (typeof FILTER_KEYS)[number];

const SEARCH_DELAY_MS = 300;

const positiveInt = (value: string | null) => {
  const n = Number(value);
  return value && Number.isInteger(n) && n > 0 ? n : undefined;
};
const isoDate = (value: string | null) =>
  value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;

/** Contract filters from the page URL; the manager filter only for supervisors and admins. */
export function filtersFromParams(params: URLSearchParams, canFilterManager: boolean): ContractFilters {
  return {
    q: params.get("q") ?? undefined,
    university_id: positiveInt(params.get("university_id")),
    it_product_id: positiveInt(params.get("it_product_id")),
    it_direction_id: positiveInt(params.get("it_direction_id")),
    manager_user_id: canFilterManager ? positiveInt(params.get("manager_user_id")) : undefined,
    transfer_status: params.get("transfer_status") || undefined,
    signed_from: isoDate(params.get("signed_from")),
    signed_to: isoDate(params.get("signed_to")),
    offset: Number(params.get("offset")) > 0 ? Math.floor(Number(params.get("offset"))) : 0,
  };
}

export function ContractsPage() {
  const { user } = useSession();
  const canEdit = canEditCatalog(user.roles);
  const [params, setParams] = useSearchParams();
  const filters = filtersFromParams(params, canEdit);
  const [search, setSearch] = useState(filters.q ?? "");
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const universities = useUniversities();
  const directions = useItDirections();
  const products = useItProducts();
  const statuses = useTransferStatuses();
  const managers = useCrmUsers(ROLES.user, canEdit);

  /** Changes one filter in the URL (replacing history) and returns to the first page. */
  function setFilter(key: FilterKey | "offset", value: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "offset") next.delete("offset");
        return next;
      },
      { replace: true },
    );
  }

  function onSearch(value: string) {
    setSearch(value);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setFilter("q", value.trim()), SEARCH_DELAY_MS);
  }

  function resetFilters() {
    clearTimeout(searchTimer.current);
    setSearch("");
    setParams(new URLSearchParams(), { replace: true });
  }

  const hasFilters = FILTER_KEYS.some((k) => params.has(k));
  // Field filters (everything but the search box) sit behind «Фильтры»; a link that already
  // carries some opens with the panel shown, so what's applied is never hidden.
  const activeFieldFilters = FILTER_KEYS.filter((k) => k !== "q" && params.has(k)).length;
  const [filtersOpen, setFiltersOpen] = useState(activeFieldFilters > 0);
  const unassigned = !canEdit && universities.data?.length === 0;
  const value = (key: FilterKey) => params.get(key) ?? "";

  return (
    <>
      <SearchToolbar
        search={search}
        onSearch={onSearch}
        placeholder="Поиск по номеру договора, вузу, продукту или вендору"
      >
        <button
          type="button"
          className={filtersOpen ? "secondary filter-toggle selected" : "secondary filter-toggle"}
          aria-expanded={filtersOpen}
          aria-controls="contract-filters"
          onClick={() => setFiltersOpen((open) => !open)}
        >
          <Filter size={16} />
          Фильтры
          {activeFieldFilters > 0 && (
            <span className="filter-count-badge" aria-label={`Применено фильтров: ${activeFieldFilters}`}>
              {activeFieldFilters}
            </span>
          )}
        </button>
        {hasFilters && (
          <button type="button" className="filter" onClick={resetFilters}>
            <X size={16} /> Сбросить фильтры
          </button>
        )}
      </SearchToolbar>
      {filtersOpen && (
        <div className="filters" id="contract-filters" role="group" aria-label="Фильтры договоров">
          <label>
            Учебное заведение
            <select
              value={value("university_id")}
              onChange={(e) => setFilter("university_id", e.target.value)}
            >
              <option value="">Все</option>
              {universities.data?.map((u) => (
                <option value={u.id} key={u.id}>
                  {u.short_name || u.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            ИТ-направление
            <select
              value={value("it_direction_id")}
              onChange={(e) => setFilter("it_direction_id", e.target.value)}
            >
              <option value="">Все</option>
              {directions.data?.map((d) => (
                <option value={d.id} key={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            ИТ-продукт
            <select
              value={value("it_product_id")}
              onChange={(e) => setFilter("it_product_id", e.target.value)}
            >
              <option value="">Все</option>
              {products.data?.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.vendor} — {p.name}
                </option>
              ))}
            </select>
          </label>
          {canEdit && (
            <label>
              Менеджер
              <select
                value={value("manager_user_id")}
                onChange={(e) => setFilter("manager_user_id", e.target.value)}
              >
                <option value="">Все</option>
                {managers.data?.map((m) => (
                  <option value={m.id} key={m.id}>
                    {m.full_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Статус передачи
            <select
              value={value("transfer_status")}
              onChange={(e) => setFilter("transfer_status", e.target.value)}
            >
              <option value="">Все</option>
              {statuses.data?.map((s) => (
                <option value={s.value} key={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Подписан с
            <input
              type="date"
              value={value("signed_from")}
              max={value("signed_to") || undefined}
              onChange={(e) => setFilter("signed_from", e.target.value)}
            />
          </label>
          <label>
            Подписан по
            <input
              type="date"
              value={value("signed_to")}
              min={value("signed_from") || undefined}
              onChange={(e) => setFilter("signed_to", e.target.value)}
            />
          </label>
        </div>
      )}
      <section className="panel">
        {unassigned ? (
          <p className="empty">{NO_UNIVERSITIES_TEXT}</p>
        ) : (
          <ContractsTable
            filters={filters}
            onOffset={(offset) => setFilter("offset", offset ? String(offset) : "")}
          />
        )}
      </section>
    </>
  );
}
