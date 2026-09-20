import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { invalidateAudit } from "./queries";
import type { NamedRef, Page, PersonRef } from "./types";

/* Types of backend/app/task_routes.py (docs/design/tasks.md) */

export type TaskStatus =
  | "new"
  | "in_progress"
  | "awaiting_review"
  | "completed"
  | "deferred"
  | "cancelled";

export type TaskPriority = "low" | "normal" | "high" | "urgent";

export type TaskScope =
  | "mine"
  | "assigned"
  | "created"
  | "participating"
  | "observing"
  | "team"
  | "all";

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  new: "Новая",
  in_progress: "В работе",
  awaiting_review: "На проверке",
  completed: "Завершена",
  deferred: "Отложена",
  cancelled: "Отменена",
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Низкий",
  normal: "Обычный",
  high: "Высокий",
  urgent: "Срочный",
};

export const TASK_SCOPE_LABELS: Record<TaskScope, string> = {
  mine: "Мои задачи",
  assigned: "Назначено мне",
  created: "Созданные мной",
  participating: "Я участвую",
  observing: "Я наблюдаю",
  team: "Задачи команды",
  all: "Все задачи",
};

/** Scope tabs shown in the UI, in display order. `created`/`observing` stay fully supported by the
 * API/backend (D-192) — just not offered as a tab; an old link using either still works (TasksPage
 * falls back to `mine` for any scope outside this list rather than crashing). */
export const VISIBLE_TASK_SCOPES: TaskScope[] = ["mine", "assigned", "participating", "team", "all"];

export interface TaskLaunchRef {
  id: number;
  program: string;
}

export interface TaskContractRef {
  id: number;
  contract_number: string;
}

export interface TaskListItem {
  id: number;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  deadline: string | null;
  creator: PersonRef | null;
  assignees: PersonRef[];
  university: NamedRef | null;
  created_at: string;
  version: number;
}

export interface ChecklistItem {
  id: number;
  title: string;
  position: number;
  is_done: boolean;
  assignee: PersonRef | null;
  deadline: string | null;
  completed_by: PersonRef | null;
  completed_at: string | null;
}

export interface TaskRef {
  id: number;
  title: string;
  status: TaskStatus;
}

export interface Task {
  id: number;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  deadline: string | null;
  planned_start: string | null;
  creator: PersonRef | null;
  university: NamedRef | null;
  interaction: TaskLaunchRef | null;
  contract: TaskContractRef | null;
  assignees: PersonRef[];
  participants: PersonRef[];
  observers: PersonRef[];
  approval_required: boolean;
  require_checklist_complete: boolean;
  checklist: ChecklistItem[];
  parent: TaskRef | null;
  subtasks: { total: number; completed: number };
  created_at: string;
  updated_at: string;
  version: number;
}

export interface TaskComment {
  id: number;
  author: PersonRef | null;
  body: string;
  created_at: string;
  attachments: { id: number; filename: string; content_type: string; size_bytes: number }[];
}

export interface TaskActivityEvent {
  id: number;
  event_type: string;
  actor: PersonRef | null;
  from_value: string | null;
  to_value: string | null;
  comment: string;
  created_at: string;
}

/** Transitions the backend may allow from each status; the server is the source of truth (docs/design/tasks.md). */
export const NEXT_STATUSES: Record<TaskStatus, TaskStatus[]> = {
  new: ["in_progress", "deferred", "cancelled"],
  in_progress: ["awaiting_review", "completed", "deferred", "cancelled"],
  awaiting_review: ["completed", "in_progress"],
  deferred: ["in_progress", "cancelled"],
  completed: ["in_progress"],
  cancelled: [],
};

/** Per-(from,to) label — the same target status reads differently depending on where it came from. Shared by
 * the quick status buttons (TaskStatusActions) and the "Мой план" board (drag or its keyboard alternative). */
export const TRANSITION_LABELS: Partial<Record<TaskStatus, Partial<Record<TaskStatus, string>>>> = {
  new: { in_progress: "Начать", deferred: "Отложить", cancelled: "Отменить" },
  in_progress: { awaiting_review: "Отправить на проверку", completed: "Завершить", deferred: "Отложить", cancelled: "Отменить" },
  awaiting_review: { completed: "Принять", in_progress: "Вернуть на доработку" },
  deferred: { in_progress: "Возобновить", cancelled: "Отменить" },
  completed: { in_progress: "Открыть заново" },
};

/** Transitions where the server requires a non-empty comment (returning work needs a reason). */
export const NEEDS_COMMENT = new Set<string>(["awaiting_review:in_progress"]);

/** Statuses shown as columns on the personal "Мой план" board — every status except the terminal
 * `cancelled`, which belongs in the List/Deadline views, not day-to-day personal planning. */
export const PLANNER_STATUSES: TaskStatus[] = ["new", "in_progress", "awaiting_review", "deferred", "completed"];

/* Queries */

export type DeadlinePreset = "overdue" | "today" | "this_week" | "next_week" | "no_deadline";

/** Shared by the List view, counters and Deadline view — the three must agree on what a filter means. */
export interface TaskFilterParams {
  status?: TaskStatus[];
  priority?: TaskPriority[];
  creator_id?: number;
  assignee_id?: number;
  participant_id?: number;
  observer_id?: number;
  university_id?: number;
  launch_id?: number;
  contract_id?: number;
  deadline_from?: string;
  deadline_to?: string;
  deadline_preset?: DeadlinePreset;
  created_from?: string;
  created_to?: string;
  has_checklist?: boolean;
  active?: boolean;
}

export interface TaskListParams extends TaskFilterParams {
  scope?: TaskScope;
  search?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

const taskListKey = (params: TaskListParams) => ["tasks", "list", params] as const;
export const taskDetailKey = (id: number) => ["tasks", "detail", id] as const;

function appendFilterParams(query: URLSearchParams, filters: TaskFilterParams) {
  for (const value of filters.status ?? []) query.append("status", value);
  for (const value of filters.priority ?? []) query.append("priority", value);
  if (filters.creator_id != null) query.set("creator_id", String(filters.creator_id));
  if (filters.assignee_id != null) query.set("assignee_id", String(filters.assignee_id));
  if (filters.participant_id != null) query.set("participant_id", String(filters.participant_id));
  if (filters.observer_id != null) query.set("observer_id", String(filters.observer_id));
  if (filters.university_id != null) query.set("university_id", String(filters.university_id));
  if (filters.launch_id != null) query.set("launch_id", String(filters.launch_id));
  if (filters.contract_id != null) query.set("contract_id", String(filters.contract_id));
  if (filters.deadline_from) query.set("deadline_from", filters.deadline_from);
  if (filters.deadline_to) query.set("deadline_to", filters.deadline_to);
  if (filters.deadline_preset) query.set("deadline_preset", filters.deadline_preset);
  if (filters.created_from) query.set("created_from", filters.created_from);
  if (filters.created_to) query.set("created_to", filters.created_to);
  if (filters.has_checklist != null) query.set("has_checklist", String(filters.has_checklist));
  if (filters.active != null) query.set("active", String(filters.active));
}

function taskListQuery(params: TaskListParams): string {
  const query = new URLSearchParams();
  if (params.scope) query.set("scope", params.scope);
  if (params.search) query.set("search", params.search);
  if (params.sort) query.set("sort", params.sort);
  if (params.limit != null) query.set("limit", String(params.limit));
  if (params.offset != null) query.set("offset", String(params.offset));
  appendFilterParams(query, params);
  const qs = query.toString();
  return qs ? `/tasks?${qs}` : "/tasks";
}

export const useTaskList = (params: TaskListParams = {}, enabled = true) =>
  useQuery({
    queryKey: taskListKey(params),
    queryFn: () => apiRequest<Page<TaskListItem>>(taskListQuery(params)),
    enabled,
  });

export interface TaskCounters {
  open: number;
  overdue: number;
  due_today: number;
  awaiting_review: number;
  no_deadline: number;
}

export const useTaskCounters = (scope: TaskScope = "mine") =>
  useQuery({
    queryKey: ["tasks", "counters", scope] as const,
    queryFn: () => apiRequest<TaskCounters>(`/tasks/counters?scope=${scope}`),
  });

export type DeadlineGroupKey = "overdue" | "today" | "this_week" | "next_week" | "later" | "no_deadline" | "completed";

export const DEADLINE_GROUP_LABELS: Record<DeadlineGroupKey, string> = {
  overdue: "Просрочено",
  today: "Сегодня",
  this_week: "На этой неделе",
  next_week: "На следующей неделе",
  later: "Позже",
  no_deadline: "Без срока",
  completed: "Завершено",
};

export interface DeadlineGroup {
  group: DeadlineGroupKey;
  total: number;
  items: TaskListItem[];
}

export interface DeadlineGroupsParams extends TaskFilterParams {
  scope?: TaskScope;
  search?: string;
}

export const useDeadlineGroups = (params: DeadlineGroupsParams = {}, enabled = true) => {
  const query = new URLSearchParams();
  if (params.scope) query.set("scope", params.scope);
  if (params.search) query.set("search", params.search);
  appendFilterParams(query, params);
  const qs = query.toString();
  return useQuery({
    queryKey: ["tasks", "deadline-groups", params] as const,
    queryFn: () => apiRequest<DeadlineGroup[]>(qs ? `/tasks/deadline-groups?${qs}` : "/tasks/deadline-groups"),
    enabled,
  });
};

/** The subset of TaskFilterParams the filter dialog exposes and saves — matches the backend's
 * `SavedFilterIn` field-for-field (task_routes.py). */
export type SavedFilterSet = Pick<
  TaskFilterParams,
  "status" | "priority" | "university_id" | "deadline_preset" | "active" | "has_checklist"
>;

export type FilterView = "list" | "deadlines";

/** The key a saved filter set is stored under — one per {view, scope} combination. */
export const filterKey = (view: FilterView, scope: TaskScope): string => `${view}:${scope}`;

export interface TaskPreferences {
  list_columns: string[] | null;
  planner_columns: TaskStatus[] | null;
  planner_positions: Record<string, number[]> | null;
  filters: Record<string, SavedFilterSet> | null;
}

export const useTaskPreferences = () =>
  useQuery({
    queryKey: ["tasks", "preferences"] as const,
    queryFn: () => apiRequest<TaskPreferences>("/tasks/preferences"),
  });

/** Each field is saved independently server-side — the List view's column picker, the planner's column
 * picker and its drag positions, and the filter dialog each call this with only the field they own, so
 * unsent fields keep their last saved value instead of being reset. `filters` is additionally merged
 * key-by-key server-side: saving one {view,scope} entry never drops another one. */
export interface TaskPreferencesPatch {
  list_columns?: string[];
  planner_columns?: TaskStatus[];
  planner_positions?: Record<string, number[]>;
  filters?: Record<string, SavedFilterSet>;
}

export function useSaveTaskPreferences() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: TaskPreferencesPatch) => apiRequest<TaskPreferences>("/tasks/preferences", "PUT", patch),
    onSuccess: (data) => client.setQueryData(["tasks", "preferences"], data),
  });
}

/** Every active CRM user, for the assignee/participant/observer pickers (any signed-in user may call this). */
export const useAssignableUsers = () =>
  useQuery({
    queryKey: ["tasks", "assignable-users"] as const,
    queryFn: () => apiRequest<PersonRef[]>("/tasks/assignable-users"),
  });

export const useTask = (id: number) =>
  useQuery({
    queryKey: taskDetailKey(id),
    queryFn: () => apiRequest<Task>(`/tasks/${id}`),
    enabled: Number.isInteger(id) && id > 0,
  });

/**
 * Broadly invalidates every cached list (many different filter/sort/scope combinations may be
 * cached at once) and the given detail query, unlike `invalidate()` in api/queries.ts which only
 * targets one exact key.
 */
function afterTaskChange(client: QueryClient, id?: number) {
  void client.invalidateQueries({ queryKey: ["tasks", "list"] });
  if (id !== undefined) void client.invalidateQueries({ queryKey: taskDetailKey(id), exact: true });
  invalidateAudit(client);
}

/* Mutations */

export interface TaskCreateInput {
  title: string;
  description?: string;
  deadline?: string | null;
  planned_start?: string | null;
  priority?: TaskPriority;
  university_id?: number | null;
  launch_id?: number | null;
  contract_id?: number | null;
  approval_required?: boolean;
  require_checklist_complete?: boolean;
  creator_id?: number | null;
  parent_task_id?: number | null;
  assignee_ids?: number[];
  participant_ids?: number[];
  observer_ids?: number[];
}

export function useCreateTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: TaskCreateInput) => apiRequest<Task>("/tasks", "POST", data),
    onSuccess: () => afterTaskChange(client),
  });
}

export interface TaskPatchInput {
  version: number;
  title?: string;
  description?: string;
  deadline?: string | null;
  planned_start?: string | null;
  priority?: TaskPriority;
  approval_required?: boolean;
}

export function useUpdateTask(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: TaskPatchInput) => apiRequest<Task>(`/tasks/${id}`, "PATCH", data),
    onSuccess: () => afterTaskChange(client, id),
  });
}

export interface TaskMembersInput {
  assignee_ids: number[];
  participant_ids: number[];
  observer_ids: number[];
}

export function useSetTaskMembers(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: TaskMembersInput) => apiRequest<Task>(`/tasks/${id}/members`, "PUT", data),
    onSuccess: () => afterTaskChange(client, id),
  });
}

export function useChangeTaskStatus(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { to_status: TaskStatus; comment?: string; version: number }) =>
      apiRequest<Task>(`/tasks/${id}/status`, "POST", data),
    onSuccess: () => afterTaskChange(client, id),
  });
}

/** Same endpoint as `useChangeTaskStatus`, but the task id is part of the mutate call instead of the
 * hook's closure — for the "Мой план" board, where a single drag-and-drop handler moves whichever
 * card was just dropped, not one task known ahead of time. */
export function useMoveTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: number; to_status: TaskStatus; comment?: string; version: number }) =>
      apiRequest<Task>(`/tasks/${id}/status`, "POST", data),
    onSuccess: (_data, vars) => afterTaskChange(client, vars.id),
  });
}

/* Checklist */

export function useAddChecklistItem(taskId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { title: string; assignee_user_id?: number | null; deadline?: string | null }) =>
      apiRequest<ChecklistItem>(`/tasks/${taskId}/checklist-items`, "POST", data),
    onSuccess: () => afterTaskChange(client, taskId),
  });
}

export function useUpdateChecklistItem(taskId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: number; title?: string; assignee_user_id?: number | null; deadline?: string | null; is_done?: boolean }) =>
      apiRequest<ChecklistItem>(`/checklist-items/${id}`, "PATCH", data),
    onSuccess: () => afterTaskChange(client, taskId),
  });
}

export function useDeleteChecklistItem(taskId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiRequest<void>(`/checklist-items/${id}`, "DELETE"),
    onSuccess: () => afterTaskChange(client, taskId),
  });
}

export function useReorderChecklist(taskId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: number[]) =>
      apiRequest<ChecklistItem[]>(`/tasks/${taskId}/checklist-order`, "PUT", { item_ids: itemIds }),
    onSuccess: () => afterTaskChange(client, taskId),
  });
}

/* Subtasks */

export const useSubtasks = (taskId: number) =>
  useQuery({
    queryKey: ["tasks", "subtasks", taskId] as const,
    queryFn: () => apiRequest<TaskListItem[]>(`/tasks/${taskId}/subtasks`),
    enabled: Number.isInteger(taskId) && taskId > 0,
  });

/* Comments */

export const useComments = (taskId: number) =>
  useQuery({
    queryKey: ["tasks", "comments", taskId] as const,
    queryFn: () => apiRequest<TaskComment[]>(`/tasks/${taskId}/comments`),
    enabled: Number.isInteger(taskId) && taskId > 0,
  });

export function useAddComment(taskId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ body, files }: { body: string; files: File[] }) => {
      const form = new FormData();
      form.append("body", body);
      for (const file of files) form.append("files", file, file.name);
      return apiRequest<TaskComment>(`/tasks/${taskId}/comments`, "POST", form);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["tasks", "comments", taskId], exact: true });
      afterTaskChange(client, taskId);
    },
  });
}

/* Activity */

export const useActivity = (taskId: number) =>
  useQuery({
    queryKey: ["tasks", "activity", taskId] as const,
    queryFn: () => apiRequest<TaskActivityEvent[]>(`/tasks/${taskId}/activity`),
    enabled: Number.isInteger(taskId) && taskId > 0,
  });

/* Bulk actions — the server checks permission per task; a selection can partially succeed. */

export interface BulkResult {
  updated: number[];
  skipped: { id: number; reason: string }[];
}

function afterBulkChange(client: QueryClient) {
  void client.invalidateQueries({ queryKey: ["tasks"] });
}

export function useBulkStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { task_ids: number[]; to_status: TaskStatus; comment?: string }) =>
      apiRequest<BulkResult>("/tasks/bulk/status", "POST", data),
    onSuccess: () => afterBulkChange(client),
  });
}

export function useBulkDeadline() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { task_ids: number[]; deadline: string | null }) =>
      apiRequest<BulkResult>("/tasks/bulk/deadline", "POST", data),
    onSuccess: () => afterBulkChange(client),
  });
}

export function useBulkMembers() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { task_ids: number[]; add_assignee_ids?: number[]; remove_assignee_ids?: number[] }) =>
      apiRequest<BulkResult>("/tasks/bulk/members", "POST", data),
    onSuccess: () => afterBulkChange(client),
  });
}

export function useBulkArchive() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { task_ids: number[]; confirm: boolean }) =>
      apiRequest<BulkResult>("/tasks/bulk/archive", "POST", data),
    onSuccess: () => afterBulkChange(client),
  });
}

export function useBulkRestore() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (task_ids: number[]) => apiRequest<BulkResult>("/tasks/bulk/restore", "POST", { task_ids }),
    onSuccess: () => afterBulkChange(client),
  });
}
