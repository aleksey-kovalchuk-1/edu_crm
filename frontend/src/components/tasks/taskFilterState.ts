import { paths } from "../../app/navigation";
import type { DeadlineGroupKey, DeadlinePreset, SavedFilterSet, TaskPriority, TaskStatus } from "../../api/tasks";

export type FilterPatch = Record<string, string | string[] | null>;

/** The six URL dimensions the filter dialog owns — kept in one place so the "is anything applied"
 * checks below and the dialog/summary components never drift out of sync with each other. */
const FILTER_KEYS = ["status", "priority", "university_id", "deadline_preset", "active", "has_checklist"] as const;

/** Whether any filter dimension is explicitly present in the URL — a shared/bookmarked link with
 * filters in it takes precedence over a saved preference (docs/design/tasks.md). */
export function hasExplicitFilters(params: URLSearchParams): boolean {
  return FILTER_KEYS.some((key) => params.has(key));
}

/** Total count for the "Фильтры" button's badge: each status/priority value counts once, each of the
 * other four dimensions counts at most once. */
export function activeFilterCount(params: URLSearchParams): number {
  return (
    params.getAll("status").length +
    params.getAll("priority").length +
    (params.get("university_id") ? 1 : 0) +
    (params.get("deadline_preset") ? 1 : 0) +
    (params.get("active") ? 1 : 0) +
    (params.get("has_checklist") ? 1 : 0)
  );
}

/** The filters currently applied in the URL, as a draft the dialog can start editing from. */
export function filtersFromParams(params: URLSearchParams): SavedFilterSet {
  return {
    status: params.getAll("status") as TaskStatus[],
    priority: params.getAll("priority") as TaskPriority[],
    university_id: params.get("university_id") ? Number(params.get("university_id")) : undefined,
    deadline_preset: (params.get("deadline_preset") as DeadlinePreset) || undefined,
    active: params.has("active") ? params.get("active") === "true" : undefined,
    has_checklist: params.has("has_checklist") ? params.get("has_checklist") === "true" : undefined,
  };
}

/** A saved/draft filter set as a patch for TasksPage's URL `update()` — every dimension is written
 * explicitly (cleared to null when unset) so applying a saved or draft set always fully replaces
 * whatever was in the URL before, rather than merging with it. */
export function savedFilterToPatch(filters: SavedFilterSet): FilterPatch {
  return {
    status: filters.status ?? [],
    priority: filters.priority ?? [],
    university_id: filters.university_id != null ? String(filters.university_id) : null,
    deadline_preset: filters.deadline_preset ?? null,
    active: filters.active != null ? String(filters.active) : null,
    has_checklist: filters.has_checklist != null ? String(filters.has_checklist) : null,
  };
}

/** Every Deadline-board group except `completed` maps 1:1 onto a `deadline_preset` value the List
 * view already understands (D-196 extended the preset enum with `later` for exactly this). */
const GROUP_TO_PRESET: Partial<Record<DeadlineGroupKey, DeadlinePreset>> = {
  overdue: "overdue",
  today: "today",
  this_week: "this_week",
  next_week: "next_week",
  later: "later",
  no_deadline: "no_deadline",
};

/**
 * The List-view link behind a Deadline-board group's "и ещё N…" note, so a group truncated at the
 * server's per-group cap is actually reachable instead of a dead end. Keeps every other applied filter
 * (search, priority, university, scope, ...) and only replaces the date/status dimension with the one
 * that exactly matches the clicked group, switching back to the List view.
 */
export function deadlineGroupListLink(params: URLSearchParams, group: DeadlineGroupKey): string {
  const next = new URLSearchParams(params);
  next.delete("view");
  next.delete("offset");
  next.delete("status");
  next.delete("deadline_preset");
  if (group === "completed") {
    next.set("status", "completed");
  } else {
    const preset = GROUP_TO_PRESET[group];
    if (preset) next.set("deadline_preset", preset);
  }
  const qs = next.toString();
  return qs ? `${paths.tasks}?${qs}` : paths.tasks;
}
