import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ListTree, Plus } from "lucide-react";
import {
  TASK_SCOPE_LABELS,
  useDeadlineGroups,
  useSaveTaskPreferences,
  useTaskList,
  useTaskPreferences,
  type DeadlinePreset,
  type TaskPriority,
  type TaskScope,
  type TaskStatus,
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
import { TaskDeadlineView } from "../components/tasks/TaskDeadlineView";
import { TaskFilterBar, type FilterPatch } from "../components/tasks/TaskFilterBar";
import { TaskListView } from "../components/tasks/TaskListView";
import { TaskPlannerView } from "../components/tasks/TaskPlannerView";

const PAGE_SIZE = 25;

const SCOPE_TABS: TabItem[] = (
  ["mine", "assigned", "created", "participating", "observing", "team", "all"] as TaskScope[]
).map((id) => ({ id, label: TASK_SCOPE_LABELS[id] }));

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
  const scope = (params.get("scope") as TaskScope) || "mine";
  const search = params.get("q") || "";
  const sort = params.get("sort") || "-created_at";
  const offset = Number(params.get("offset") || 0);
  const filters = {
    status: params.getAll("status") as TaskStatus[],
    priority: params.getAll("priority") as TaskPriority[],
    university_id: params.get("university_id") ? Number(params.get("university_id")) : undefined,
    deadline_preset: (params.get("deadline_preset") as DeadlinePreset) || undefined,
    active: params.has("active") ? params.get("active") === "true" : undefined,
    has_checklist: params.has("has_checklist") ? params.get("has_checklist") === "true" : undefined,
  };

  const preferences = useTaskPreferences();
  const savePreferences = useSaveTaskPreferences();
  const columns = preferences.data?.list_columns ?? DEFAULT_COLUMNS;

  const list = useTaskList({ scope, search, sort, limit: PAGE_SIZE, offset, ...filters }, view === "list");
  const deadlineGroups = useDeadlineGroups({ scope, search, ...filters }, view === "deadlines");
  // The planner view manages its own queries/loading state (TaskPlannerView) — it isn't scoped by
  // this page's search/sort/filter bar, so it has no "active query" here.
  const activeQuery = view === "list" ? list : view === "deadlines" ? deadlineGroups : null;
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

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
      <Tabs label="Представление" tabs={VIEWS} selected={view} onSelect={(id) => update({ view: id === "list" ? null : id })}>
        {view === "planner" ? (
          <TaskPlannerView />
        ) : (
          <Tabs label="Область видимости" tabs={SCOPE_TABS} selected={scope} onSelect={(id) => update({ scope: id === "mine" ? null : id })}>
            <SearchToolbar
              search={search}
              onSearch={(value) => update({ q: value || null })}
              placeholder="Поиск по названию или описанию"
              count={view === "list" ? list.data?.total : undefined}
            >
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
            <TaskFilterBar params={params} onUpdate={update} />
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
            {view === "deadlines" && deadlineGroups.data && <TaskDeadlineView groups={deadlineGroups.data} />}
          </Tabs>
        )}
      </Tabs>
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
