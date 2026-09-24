import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, LIST_ITEM_DEFAULTS } from "../test/utils";

const change = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });

const PLANNER_TASKS = [
  {
    id: 1,
    title: "Собрать документы",
    status: "new",
    priority: "normal",
    deadline: null,
    creator: null,
    assignees: [{ id: 5, full_name: "Анна Демо" }],
    university: null,
    created_at: "2026-09-01T10:00:00Z",
    ...LIST_ITEM_DEFAULTS,
    version: 1,
  },
  {
    id: 4,
    title: "Согласовать доступ",
    status: "new",
    priority: "high",
    deadline: null,
    creator: null,
    assignees: [],
    university: null,
    created_at: "2026-09-02T10:00:00Z",
    ...LIST_ITEM_DEFAULTS,
    version: 1,
  },
  {
    id: 2,
    title: "Написать письмо",
    status: "in_progress",
    priority: "normal",
    deadline: null,
    creator: null,
    assignees: [],
    university: null,
    created_at: "2026-09-01T10:00:00Z",
    ...LIST_ITEM_DEFAULTS,
    version: 2,
  },
  {
    id: 3,
    title: "Проверить данные",
    status: "awaiting_review",
    priority: "normal",
    deadline: null,
    creator: null,
    assignees: [],
    university: null,
    created_at: "2026-09-01T10:00:00Z",
    ...LIST_ITEM_DEFAULTS,
    version: 5,
  },
];

async function openPlanner() {
  fireEvent.click(await screen.findByRole("tab", { name: "Мой план" }));
}

const columnOf = async (heading: string) =>
  (await screen.findByRole("heading", { name: heading })).closest(".planner-column") as HTMLElement;

describe("task planner: board", () => {
  it("buckets cards into columns by status", async () => {
    mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: PLANNER_TASKS.length, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();

    const newColumn = await columnOf("Новая");
    expect(within(newColumn).getByText("Собрать документы")).toBeTruthy();
    expect(within(newColumn).getByText("Согласовать доступ")).toBeTruthy();
    const inProgressColumn = await columnOf("В работе");
    expect(within(inProgressColumn).getByText("Написать письмо")).toBeTruthy();
    expect(within(inProgressColumn).queryByText("Собрать документы")).toBeNull();
  });
});

describe("task planner: moving cards", () => {
  it("moves a card to the next status via the explicit select when no comment is required", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: PLANNER_TASKS.length, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    await columnOf("Новая");

    change(screen.getByLabelText("Переместить «Собрать документы»"), "in_progress");

    await waitFor(() => expect(api.count("POST", "/tasks/1/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks/1/status")?.body).toEqual({
      to_status: "in_progress",
      comment: "",
      version: 1,
    });
  });

  it("prompts for a required comment before returning a card to work", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: PLANNER_TASKS.length, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    await columnOf("На проверке");

    change(screen.getByLabelText("Переместить «Проверить данные»"), "in_progress");
    fireEvent.change(await screen.findByLabelText("Что нужно исправить"), { target: { value: "Не хватает подписи" } });
    fireEvent.click(screen.getByRole("button", { name: "Вернуть" }));

    await waitFor(() => expect(api.count("POST", "/tasks/3/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks/3/status")?.body).toEqual({
      to_status: "in_progress",
      comment: "Не хватает подписи",
      version: 5,
    });
  });
});

describe("task planner: manual ordering", () => {
  it("reorders cards within a column and saves the new order", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: PLANNER_TASKS.length, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    await columnOf("Новая");

    fireEvent.click(screen.getByRole("button", { name: "Переместить «Собрать документы» ниже в колонке" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT" && c.path === "/tasks/preferences")?.body).toEqual({
      planner_positions: { new: [4, 1] },
    });
  });
});

describe("task planner: column settings", () => {
  it("hides a column and persists the visible/order preference", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: PLANNER_TASKS.length, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    await columnOf("Новая");

    fireEvent.click(screen.getByText("Колонки плана"));
    fireEvent.click(screen.getByLabelText("Завершена"));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT" && c.path === "/tasks/preferences")?.body).toEqual({
      planner_columns: ["new", "in_progress", "awaiting_review", "deferred"],
    });
  });

  it("moves a column to a different position", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: PLANNER_TASKS.length, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    await columnOf("Новая");

    fireEvent.click(screen.getByText("Колонки плана"));
    fireEvent.click(screen.getByRole("button", { name: "Сдвинуть колонку «Новая» правее" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT" && c.path === "/tasks/preferences")?.body).toEqual({
      planner_columns: ["in_progress", "new", "awaiting_review", "deferred", "completed"],
    });
  });
});
