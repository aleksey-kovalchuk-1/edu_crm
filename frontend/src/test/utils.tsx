import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { vi } from "vitest";
import type { Session } from "../api/auth";
import { API_BASE } from "../api/client";
import type {
  Contract,
  CrmUser,
  Dashboard,
  ITDirection,
  ITProduct,
  Launch,
  Task,
  TransferStatus,
  University,
  UniversityContact,
} from "../api/types";
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
    },
  ];
  const tasks: Task[] = [
    {
      id: 1,
      launch_id: 1,
      title: "Согласовать договор",
      owner: "Ирина Петрова",
      deadline: "2026-09-20",
      done: false,
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
    tasks,
    stages,
    dashboard,
    directions,
    products,
    users,
    contacts,
    transferStatuses,
    contracts,
  };
}

export const CSRF_TOKEN = "csrf-test-token";

export const sessionFixture = (
  roles: string[] = ["crm-supervisor"],
  csrfToken = CSRF_TOKEN,
): Session => ({
  user: {
    id: 1,
    email: "anna.petrova@example.test",
    full_name: "Анна Петрова",
    roles,
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
  const handlers: Record<string, Handler> = {
    "GET /auth/me": () => sessionFixture(),
    [`GET ${AUDIT_PATH}`]: () => [],
    "GET /universities": () => data.universities,
    "GET /launches": () => data.launches,
    "GET /tasks": () => data.tasks,
    "GET /stages": () => data.stages,
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
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
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
