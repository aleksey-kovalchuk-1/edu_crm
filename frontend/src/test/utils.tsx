import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { vi } from "vitest";
import type { Session } from "../api/auth";
import { API_BASE } from "../api/client";
import type { PlanRun, PlanTemplate } from "../api/planTemplates";
import type { Task, TaskListItem, TaskPreferences } from "../api/tasks";
import type {
  Contract,
  CrmUser,
  Dashboard,
  ITDirection,
  ITProduct,
  Launch,
  TransferStatus,
  University,
  UniversityContact,
} from "../api/types";
import type { Workflow } from "../api/workflows";
import { AppProviders } from "../app/AppProviders";
import { AppRoutes } from "../app/App";
import { createQueryClient } from "../app/queryClient";

export function fixtures() {
  const universities: University[] = [
    {
      id: 1,
      name: "Колледж связи",
      short_name: "КС",
      city: "Казань",
      region: "Республика Татарстан",
      website: "https://ks.example",
      contact: "Анна Смирнова",
      is_active: true,
      managers: [{ id: 5, full_name: "Анна Демо" }],
    },
    {
      id: 2,
      name: "Технический университет",
      short_name: "",
      city: "Омск",
      region: "",
      website: "",
      contact: "",
      is_active: true,
      managers: [],
    },
  ];
  const directions: ITDirection[] = [
    { id: 1, name: "DevOps", description: "", is_active: true },
    { id: 2, name: "Тестирование", description: "QA", is_active: true },
  ];
  const products: ITProduct[] = [
    {
      id: 3,
      vendor: "РТК ИТ",
      name: "Учебная среда",
      description: "",
      is_active: true,
      directions: [{ id: 1, name: "DevOps" }],
    },
  ];
  const users: CrmUser[] = [
    { id: 5, full_name: "Анна Демо", email: "anna@example.test", roles: ["crm-user"], is_active: true },
    { id: 6, full_name: "Олег Кузнецов", email: "oleg@example.test", roles: ["crm-user"], is_active: true },
  ];
  const contacts: UniversityContact[] = [
    {
      id: 7,
      university_id: 1,
      full_name: "Иван Демо",
      position: "Проректор",
      email: "",
      phone: "",
      comment: "",
      is_active: true,
    },
  ];
  const transferStatuses: TransferStatus[] = [
    { value: "not_started", label: "Не начата" },
    { value: "in_progress", label: "Идёт передача" },
    { value: "transferred", label: "Передано" },
    { value: "cancelled", label: "Отменено" },
  ];
  const contracts: Contract[] = [
    {
      id: 12,
      contract_number: "Д-2026-001",
      university: { id: 1, name: "Колледж связи" },
      it_product: { id: 3, vendor: "РТК ИТ", name: "Учебная среда" },
      signed_at: "2025-10-01",
      valid_until: "2026-10-01",
      transfer_status: "in_progress",
      transfer_status_label: "Идёт передача",
      manager: { id: 5, full_name: "Анна Демо" },
      manager_name: "",
      contacts: [{ id: 7, full_name: "Иван Демо" }],
      comment: "",
      is_expired: false,
      expires_soon: true,
      updated_at: "2026-09-01T10:00:00Z",
    },
  ];
  const launches: Launch[] = [
    {
      id: 1,
      university_id: 1,
      university: "Колледж связи",
      city: "Казань",
      program: "Аналитика данных",
      product: "PostgreSQL",
      owner: "Ирина Петрова",
      students: 24,
      stage: 4,
      // Past deadline but not overdue per the server: the client must not recompute.
      deadline: "2020-01-01",
      overdue: false,
      workflow_template_id: 1,
      status_id: 12,
    },
    {
      id: 2,
      university_id: 2,
      university: "Технический университет",
      city: "Омск",
      program: "Облачные технологии",
      product: "Kubernetes",
      owner: "Олег Кузнецов",
      students: 30,
      stage: 7,
      deadline: "2099-01-01",
      overdue: true,
      workflow_template_id: 1,
      status_id: 14,
    },
  ];
  const workflows: Workflow[] = [
    {
      id: 1,
      name: "Типовое взаимодействие с вузом",
      description: "Базовый процесс",
      is_default: true,
      is_active: true,
      statuses: [
        { id: 11, name: "Первый контакт", position: 0, is_final: false, is_active: true },
        { id: 12, name: "Согласование документов", position: 1, is_final: false, is_active: true },
        { id: 13, name: "Архивный статус", position: 2, is_final: false, is_active: false },
        { id: 14, name: "Сопровождение", position: 3, is_final: true, is_active: true },
      ],
    },
    {
      id: 2,
      name: "Короткий процесс",
      description: "",
      is_default: false,
      is_active: true,
      statuses: [{ id: 21, name: "Старт", position: 0, is_final: true, is_active: true }],
    },
  ];
  const tasks: TaskListItem[] = [
    {
      id: 1,
      title: "Согласовать договор",
      status: "new",
      priority: "normal",
      deadline: "2026-09-20",
      creator: { id: 5, full_name: "Ирина Петрова" },
      assignees: [{ id: 5, full_name: "Ирина Петрова" }],
      university: null,
      interaction: null,
      checklist_progress: { total: 0, completed: 0 },
      subtasks: { total: 0, completed: 0 },
      comment_count: 0,
      created_at: "2026-09-01T10:00:00Z",
      updated_at: "2026-09-01T10:00:00Z",
      version: 1,
    },
  ];
  const task: Task = {
    id: 1,
    title: "Согласовать договор",
    description: "",
    status: "new",
    priority: "normal",
    deadline: "2026-09-20",
    planned_start: null,
    creator: { id: 5, full_name: "Ирина Петрова" },
    university: null,
    interaction: null,
    contract: null,
    assignees: [{ id: 5, full_name: "Ирина Петрова" }],
    participants: [],
    observers: [],
    approval_required: false,
    require_checklist_complete: true,
    checklist: [],
    parent: null,
    subtasks: { total: 0, completed: 0 },
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    version: 1,
  };
  const planTemplates: PlanTemplate[] = [
    {
      id: 1,
      name: "Адаптация нового вуза",
      description: "Типовой план запуска сотрудничества",
      is_active: true,
      created_at: "2026-01-01T10:00:00Z",
      steps: [
        {
          id: 101,
          position: 0,
          title: "Собрать документы",
          description: "",
          assignee_rule: "university_manager",
          assignee_rule_user_id: null,
          start_offset_days: 0,
          deadline_offset_days: 3,
          offset_unit: "business",
          priority: "normal",
          approval_required: false,
          is_optional: false,
          depends_on_step_id: null,
          checklist_items: [],
        },
        {
          id: 102,
          position: 1,
          title: "Подписать договор",
          description: "",
          assignee_rule: "specific_user",
          assignee_rule_user_id: 5,
          start_offset_days: 3,
          deadline_offset_days: 5,
          offset_unit: "business",
          priority: "high",
          approval_required: true,
          is_optional: false,
          depends_on_step_id: 101,
          checklist_items: [],
        },
      ],
    },
  ];
  const planRuns: PlanRun[] = [
    {
      id: 501,
      template_id: 1,
      template_name: "Адаптация нового вуза",
      university_id: 1,
      launch_id: null,
      start_date: "2026-09-01",
      started_by: { id: 5, full_name: "Анна Демо" },
      created_at: "2026-09-01T10:00:00Z",
      progress: { total: 4, completed: 1, awaiting_review: 0, overdue: 0, blocked: 1 },
    },
  ];
  // Same length as backend STAGES (13).
  const stages = Array.from({ length: 13 }, (_, i) => `Этап ${i + 1}`);
  const dashboard: Dashboard = {
    universities: 2,
    launches: 2,
    students: 54,
    overdue: 1,
    annual: [{ year: 2025, applications: 120, students: 80, streams: 4 }],
  };
  return {
    universities,
    launches,
    workflows,
    tasks,
    task,
    stages,
    dashboard,
    directions,
    products,
    users,
    contacts,
    transferStatuses,
    contracts,
    planTemplates,
    planRuns,
  };
}

export const CSRF_TOKEN = "csrf-test-token";

export const sessionFixture = (
  roles: string[] = ["crm-supervisor"],
  csrfToken = CSRF_TOKEN,
  user: { phone?: string; phone_verified_at?: string | null } = {},
): Session => ({
  user: {
    id: 1,
    email: "anna.petrova@example.test",
    full_name: "Анна Петрова",
    roles,
    phone: user.phone ?? "",
    phone_verified_at: user.phone_verified_at ?? null,
  },
  csrf_token: csrfToken,
});

export const AUDIT_PATH = "/audit/recent?limit=10";

export interface Call {
  method: string;
  path: string;
  body: unknown;
  /** Request headers with lower-case names. */
  headers: Record<string, string>;
}

/** Response body, or [status, body]; may be a promise to simulate slow or hanging requests. */
type HandlerResult = [number, unknown] | unknown;
type Handler = (call: Call) => HandlerResult | Promise<HandlerResult>;

/** A promise that never settles (a request that hangs). */
export const never = () => new Promise<never>(() => {});

/** A promise plus its resolve function, to release a request at a chosen moment. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

export const apiError = (status: number, code: string, message: string, details: unknown = null) =>
  [status, { code, message, details }] as [number, unknown];

/**
 * Stubs global fetch with an in-memory API; handlers are keyed "METHOD /path".
 * A handler for the exact path (with query) wins; otherwise the path without
 * its query string is tried.
 */
export function mockApi(extra: Record<string, Handler> = {}) {
  const data = fixtures();
  const calls: Call[] = [];
  const count = (method: string, path: string) =>
    calls.filter((c) => c.method === method && c.path === path).length;
  // Mirrors the backend's per-field-independent, filters-merged-by-key PUT /tasks/preferences (D-181,
  // D-192, D-202): each save only touches the fields the request actually sent; `filters` merges by
  // key, every other field (including the four board-layout dicts) is a plain replace.
  const storedPreferences: TaskPreferences = {
    list_columns: null, planner_columns: null, planner_positions: null,
    planner_custom_columns: null, planner_custom_members: null,
    deadline_columns: null, deadline_positions: null,
    deadline_custom_columns: null, deadline_custom_members: null,
    filters: null,
  };
  const handlers: Record<string, Handler> = {
    "GET /auth/me": () => sessionFixture(),
    [`GET ${AUDIT_PATH}`]: () => [],
    "GET /universities": () => data.universities,
    "GET /launches": () => data.launches,
    "GET /tasks": () => ({
      items: data.tasks,
      total: data.tasks.length,
      limit: 25,
      offset: 0,
    }),
    "GET /tasks/1": () => data.task,
    "GET /tasks/1/subtasks": () => [],
    "GET /tasks/1/comments": () => [],
    "GET /tasks/1/activity": () => [],
    "GET /tasks/counters": () => ({ open: 0, overdue: 0, due_today: 0, awaiting_review: 0, no_deadline: 0 }),
    "GET /tasks/preferences": () => storedPreferences,
    "PUT /tasks/preferences": (call) => {
      const body = call.body as Partial<TaskPreferences>;
      for (const key of Object.keys(body) as (keyof TaskPreferences)[]) {
        if (key === "filters") {
          storedPreferences.filters = { ...(storedPreferences.filters ?? {}), ...(body.filters ?? {}) };
        } else {
          // Every other field (list_columns, the two boards' column/position/custom dicts) is a plain
          // replace, matching the real endpoint — each field here has its own type, so a generic
          // assignment needs a cast rather than per-field branches.
          (storedPreferences as unknown as Record<string, unknown>)[key] = body[key];
        }
      }
      return storedPreferences;
    },
    "GET /tasks/assignable-users": () => data.users,
    "GET /task-plan-templates": () => data.planTemplates,
    "GET /task-plan-runs": () => data.planRuns,
    "GET /stages": () => data.stages,
    "GET /workflows": () => data.workflows,
    "GET /launches/1/status-changes": () => [],
    "GET /dashboard": () => data.dashboard,
    "GET /launches/1/history": () => [
      { id: 1, stage: 4, created_at: "2026-09-01T10:00:00" },
    ],
    "GET /it-directions": () => data.directions,
    "GET /it-products": () => data.products,
    "GET /users": () => data.users,
    "GET /universities/1/contacts": () => data.contacts,
    "GET /universities/2/contacts": () => [],
    "GET /contracts/transfer-statuses": () => data.transferStatuses,
    "GET /contracts": () => ({
      items: data.contracts,
      total: data.contracts.length,
      limit: 50,
      offset: 0,
    }),
    ...extra,
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = String(input).replace(API_BASE, "");
    const call = {
      method,
      path,
      body:
        init?.body instanceof FormData
          ? init.body
          : init?.body
            ? JSON.parse(String(init.body))
            : undefined,
      headers: Object.fromEntries(new Headers(init?.headers).entries()),
    };
    calls.push(call);
    const handler =
      handlers[`${method} ${path}`] ?? handlers[`${method} ${path.split("?")[0]}`];
    const result = handler
      ? await handler(call)
      : apiError(404, "NOT_FOUND", "Ресурс не найден");
    const [status, body] =
      Array.isArray(result) && typeof result[0] === "number" && result.length === 2
        ? (result as [number, unknown])
        : [200, result];
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  /** Calls to a path, ignoring its query string. */
  const callsTo = (method: string, pathname: string) =>
    calls.filter((c) => c.method === method && c.path.split("?")[0] === pathname);
  return { data, calls, count, callsTo };
}

/** Exposes the router location as text (data-testid="location"). */
function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="location" hidden>
      {location.pathname + location.search}
    </output>
  );
}

export function renderApp(path: string) {
  return render(
    <AppProviders client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
}
