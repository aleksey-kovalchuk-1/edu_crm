import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ListTree, Plus } from "lucide-react";
import {
  TASK_SCOPE_LABELS,
  VISIBLE_TASK_SCOPES,
  filterKey,
  useSaveTaskPreferences,
  useTaskList,
  useTaskPreferences,
  type SavedFilterSet,
  type TaskScope,
} from "../api/tasks";
import { useSession } from "../app/AuthGate";
import { paths, taskPath } from "../app/navigation";
import { canEditWorkflows } from "../lib/user";
import { TaskCreateForm } from "../components/forms/TaskCreateForm";
import { Modal } from "../components/Modal";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import { Tabs, type TabItem } from "../components/Tabs";
import { TaskBulkActionsBar } from "../components/tasks/TaskBulkActionsBar";
import { TaskColumnPicker, DEFAULT_COLUMNS } from "../components/tasks/TaskColumnPicker";
import { TaskCounters } from "../components/tasks/TaskCounters";
import { TaskDeadlineBoard } from "../components/tasks/TaskDeadlineBoard";
import { TaskFilterButton } from "../components/tasks/TaskFilterButton";
import { TaskFilterDialog } from "../components/tasks/TaskFilterDialog";
import { TaskFilterSummary } from "../components/tasks/TaskFilterSummary";
import { TaskListView } from "../components/tasks/TaskListView";
import { TaskPlannerView } from "../components/tasks/TaskPlannerView";
import { activeFilterCount, filtersFromParams, hasExplicitFilters, savedFilterToPatch, type FilterPatch } from "../components/tasks/taskFilterState";

const PAGE_SIZE = 25;

const SCOPE_TABS: TabItem[] = VISIBLE_TASK_SCOPES.map((id) => ({ id, label: TASK_SCOPE_LABELS[id] }));

/** Switching view or scope moves to a different {view, scope} filter set entirely — the six filter
 * dimensions are cleared from the URL as part of that same navigation so the restore effect below sees
 * a clean slate for the new key, rather than treating the previous key's filters as an explicit choice
 * for this one and refusing to restore anything saved for it. */
const CLEAR_FILTERS: FilterPatch = { status: [], priority: [], university_id: null, deadline_preset: null, active: null, has_checklist: null };

const SORTS: { value: string; label: string }[] = [
  { value: "-created_at", label: "Сначала новые" },
  { value: "deadline", label: "По сроку" },
  { value: "-priority", label: "По приоритету" },
  { value: "title", label: "По названию" },
];

const VIEWS: TabItem[] = [
  { id: "list", label: "Список" },
  { id: "deadlines", label: "Сроки" },
  { id: "planner", label: "Мой план" },
];

export function TasksPage() {
  const navigate = useNavigate();
  const { user } = useSession();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const filterButtonRef = useRef<HTMLButtonElement>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // Reset selection whenever the URL (view/scope/filters/page) changes, so a stale selection never
  // survives to a different visible set. Adjusted during render (React's recommended pattern for
  // "state derived from a changing key"), not in an effect, to avoid an extra render pass.
  const [selectionKey, setSelectionKey] = useState(params.toString());
  if (params.toString() !== selectionKey) {
    setSelectionKey(params.toString());
    setSelected(new Set());
  }

  const viewParam = params.get("view");
  const view = viewParam === "deadlines" || viewParam === "planner" ? viewParam : "list";
  // Any scope value the backend still accepts (e.g. an old `created`/`observing` link) but that no
  // longer has a visible tab falls back to `mine` here, rather than crashing or rendering no tab as
  // selected.
  const rawScope = params.get("scope") as TaskScope | null;
  const scope = rawScope && (VISIBLE_TASK_SCOPES as string[]).includes(rawScope) ? rawScope : "mine";
  const search = params.get("q") || "";
  const sort = params.get("sort") || "-created_at";
  const offset = Number(params.get("offset") || 0);
  const filters = filtersFromParams(params);

  const preferences = useTaskPreferences();
  const savePreferences = useSaveTaskPreferences();
  const columns = preferences.data?.list_columns ?? DEFAULT_COLUMNS;

  const list = useTaskList({ scope, search, sort, limit: PAGE_SIZE, offset, ...filters }, view === "list");
  // The Deadlines board and planner both manage their own queries/loading state internally
  // (TaskDeadlineBoard, TaskPlannerView) — they have their own useTaskList call, so neither has an
  // "active query" here.
  const activeQuery = view === "list" ? list : null;
  const fallback = activeQuery ? queryFallback([activeQuery]) : null;

  function update(patch: FilterPatch, resetOffset = true) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(patch)) {
      next.delete(key);
      if (value === null) continue;
      if (Array.isArray(value)) {
        for (const v of value) next.append(key, v);
      } else if (value !== "") {
        next.set(key, value);
      }
    }
    if (resetOffset) next.delete("offset");
    setParams(next, { replace: true });
  }

  // Restore a saved filter set for this {view, scope} the first time it's visited without any explicit
  // filter already in the URL (a shared/bookmarked filtered link always wins — docs/design/tasks.md).
  // Guarded by restoredKey so this runs at most once per {view, scope}, not on every background refetch
  // of preferences or every filter the user then applies by hand.
  const restoredKey = useRef<string | null>(null);
  useEffect(() => {
    if (view === "planner") return;
    const key = filterKey(view, scope);
    if (restoredKey.current === key || preferences.data === undefined) return;
    restoredKey.current = key;
    if (hasExplicitFilters(params)) return;
    const saved = preferences.data.filters?.[key];
    if (saved) update(savedFilterToPatch(saved));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, scope, preferences.data]);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function closeFilterDialog() {
    setFilterDialogOpen(false);
    filterButtonRef.current?.focus();
  }

  function saveFilters(draft: SavedFilterSet) {
    update(savedFilterToPatch(draft));
    if (view !== "planner") {
      savePreferences.mutate({ filters: { [filterKey(view, scope)]: draft } });
    }
    closeFilterDialog();
  }

  if (fallback) return fallback;

  return (
    <>
      {activeQuery && <RefreshError queries={[activeQuery]} />}
      {canEditWorkflows(user.roles) && (
        <div className="detail-links">
          <Link className="text-button" to={paths.taskTemplates}>
            <ListTree size={16} />
            Шаблоны планов
          </Link>
        </div>
      )}
      <TaskCounters scope={scope} onSelect={(patch) => update(patch)} />
      <Tabs
        label="Представление"
        tabs={VIEWS}
        selected={view}
        onSelect={(id) => update({ view: id === "list" ? null : id, ...CLEAR_FILTERS })}
      >
        {view === "planner" ? (
          <TaskPlannerView />
        ) : (
          <Tabs
            label="Область видимости"
            tabs={SCOPE_TABS}
            selected={scope}
            onSelect={(id) => update({ scope: id === "mine" ? null : id, ...CLEAR_FILTERS })}
          >
            <SearchToolbar
              search={search}
              onSearch={(value) => update({ q: value || null })}
              placeholder="Поиск по названию или описанию"
              count={view === "list" ? list.data?.total : undefined}
            >
              <TaskFilterButton ref={filterButtonRef} count={activeFilterCount(params)} onClick={() => setFilterDialogOpen(true)} />
              {view === "list" && (
                <label className="inline-select">
                  Сортировка
                  <select value={sort} onChange={(e) => update({ sort: e.target.value === "-created_at" ? null : e.target.value }, false)}>
                    {SORTS.map((s) => (
                      <option value={s.value} key={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {view === "list" && (
                <TaskColumnPicker columns={columns} onChange={(cols) => savePreferences.mutate({ list_columns: cols })} />
              )}
              <button type="button" className="primary" onClick={() => setCreating(true)}>
                <Plus size={18} />
                Создать задачу
              </button>
            </SearchToolbar>
            <TaskFilterSummary params={params} onUpdate={update} />
            {selected.size > 0 && (
              <TaskBulkActionsBar selectedIds={[...selected]} onDone={() => setSelected(new Set())} />
            )}
            {view === "list" && list.data && (
              <TaskListView
                items={list.data.items}
                total={list.data.total}
                limit={list.data.limit}
                offset={list.data.offset}
                columns={columns}
                selected={selected}
                onToggle={toggleSelect}
                onToggleAll={() =>
                  setSelected((prev) => {
                    const ids = list.data!.items.map((t) => t.id);
                    const allSelected = ids.every((id) => prev.has(id));
                    const next = new Set(prev);
                    for (const id of ids) {
                      if (allSelected) next.delete(id);
                      else next.add(id);
                    }
                    return next;
                  })
                }
                onPage={(next) => update({ offset: String(next) }, false)}
              />
            )}
            {view === "deadlines" && <TaskDeadlineBoard scope={scope} search={search} filters={filters} />}
          </Tabs>
        )}
      </Tabs>
      {filterDialogOpen && view !== "planner" && (
        <TaskFilterDialog
          initial={filters}
          scopeLabel={TASK_SCOPE_LABELS[scope]}
          onCancel={closeFilterDialog}
          onSave={saveFilters}
        />
      )}
      {creating && (
        <Modal title="Новая задача" close={() => setCreating(false)}>
          <TaskCreateForm
            onCreated={(task) => {
              setCreating(false);
              navigate(taskPath(task.id));
            }}
            onCancel={() => setCreating(false)}
          />
        </Modal>
      )}
    </>
  );
}
