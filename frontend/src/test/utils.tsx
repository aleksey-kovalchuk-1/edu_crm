import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { API_BASE } from "../api/client";
import type { Dashboard, Launch, Task, University } from "../api/types";
import { AppProviders } from "../app/AppProviders";
import { AppRoutes } from "../app/App";
import { createQueryClient } from "../app/queryClient";

export function fixtures() {
  const universities: University[] = [
    { id: 1, name: "Колледж связи", city: "Казань", contact: "Анна Смирнова" },
    { id: 2, name: "Технический университет", city: "Омск", contact: "" },
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
  return { universities, launches, tasks, stages, dashboard };
}

export interface Call {
  method: string;
  path: string;
  body: unknown;
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

/** Stubs global fetch with an in-memory API; handlers are keyed "METHOD /path". */
export function mockApi(extra: Record<string, Handler> = {}) {
  const data = fixtures();
  const calls: Call[] = [];
  const count = (method: string, path: string) =>
    calls.filter((c) => c.method === method && c.path === path).length;
  const handlers: Record<string, Handler> = {
    "GET /universities": () => data.universities,
    "GET /launches": () => data.launches,
    "GET /tasks": () => data.tasks,
    "GET /stages": () => data.stages,
    "GET /dashboard": () => data.dashboard,
    "GET /launches/1/history": () => [
      { id: 1, stage: 4, created_at: "2026-09-01T10:00:00" },
    ],
    ...extra,
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = String(input).replace(API_BASE, "");
    const call = {
      method,
      path,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const handler = handlers[`${method} ${path}`];
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
  return { data, calls, count };
}

export function renderApp(path: string) {
  return render(
    <AppProviders client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  );
}
