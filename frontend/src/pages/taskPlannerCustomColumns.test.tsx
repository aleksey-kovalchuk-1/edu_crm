import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const change = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });

const PLANNER_TASKS = [
  {
    id: 1,
    title: "Собрать документы",
    status: "new",
    priority: "normal",
    deadline: null,
    creator: null,
    assignees: [],
    university: null,
    created_at: "2026-09-01T10:00:00Z",
    version: 1,
  },
];

async function openPlanner() {
  fireEvent.click(await screen.findByRole("tab", { name: "Мой план" }));
}

const columnOf = async (heading: string) =>
  (await screen.findByRole("heading", { name: heading })).closest(".planner-column") as HTMLElement;

describe("task planner: custom columns", () => {
  it("adds a custom column at the end of the board", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: 1, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    await screen.findByText("Собрать документы");

    fireEvent.click(screen.getByRole("button", { name: "Добавить колонку" }));
    fireEvent.change(screen.getByLabelText("Название новой колонки"), { target: { value: "Ждём клиента" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    const body = api.calls.find((c) => c.method === "PUT")?.body as {
      planner_columns: string[];
      planner_custom_columns: Record<string, { title: string }>;
    };
    const newId = body.planner_columns.at(-1)!;
    expect(newId.startsWith("custom:")).toBe(true);
    expect(body.planner_custom_columns[newId]).toEqual({ title: "Ждём клиента" });
    expect(await screen.findByRole("heading", { name: /Ждём клиента/ })).toBeTruthy();
  });

  it("renames a custom column", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: PLANNER_TASKS, total: 1, limit: 100, offset: 0 }),
      "GET /tasks/preferences": () => ({
        list_columns: null,
        planner_columns: ["new", "in_progress", "custom:x"],
        planner_positions: null,
        planner_custom_columns: { "custom:x": { title: "Старое имя" } },
        planner_custom_members: null,
        deadline_columns: null,
        deadline_positions: null,
        deadline_custom_columns: null,
        deadline_custom_members: null,
        filters: null,
      }),
    });
    renderApp("/tasks");
    await openPlanner();
    const column = await columnOf("Старое имя");
    fireEvent.click(within(column).getByRole("button", { name: "Переименовать колонку «Старое имя»" }));
    fireEvent.change(within(column).getByLabelText("Название колонки «Старое имя»"), { target: { value: "Новое имя" } });
    fireEvent.click(within(column).getByRole("button", { name: "ОК" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      planner_custom_columns: { "custom:x": { title: "Новое имя" } },
    });
  });

  it("deletes a custom column with confirmation, returning its task to the natural column", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: PLANNER_TASKS, total: 1, limit: 100, offset: 0 }),
      "GET /tasks/preferences": () => ({
        list_columns: null,
        planner_columns: ["new", "in_progress", "custom:x"],
        planner_positions: null,
        planner_custom_columns: { "custom:x": { title: "Ждём клиента" } },
        planner_custom_members: { "1": "custom:x" },
        deadline_columns: null,
        deadline_positions: null,
        deadline_custom_columns: null,
        deadline_custom_members: null,
        filters: null,
      }),
    });
    renderApp("/tasks");
    await openPlanner();
    const custom = await columnOf("Ждём клиента");
    expect(within(custom).getByText("Собрать документы")).toBeTruthy();

    fireEvent.click(within(custom).getByRole("button", { name: "Удалить колонку «Ждём клиента»" }));
    const dialog = await screen.findByRole("dialog", { name: "Удалить колонку «Ждём клиента»?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      planner_columns: ["new", "in_progress"],
      planner_custom_columns: {},
      planner_custom_members: {},
    });
    expect(screen.queryByRole("heading", { name: /Ждём клиента/ })).toBeNull();
    const newColumn = await columnOf("Новая");
    expect(within(newColumn).getByText("Собрать документы")).toBeTruthy();
  });

  it("reorders a column with the header's move-left/move-right buttons", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: PLANNER_TASKS, total: 1, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openPlanner();
    const column = await columnOf("В работе");
    fireEvent.click(within(column).getByRole("button", { name: "Сдвинуть колонку «В работе» левее" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    const body = api.calls.find((c) => c.method === "PUT")?.body as { planner_columns: string[] };
    expect(body.planner_columns.slice(0, 2)).toEqual(["in_progress", "new"]);
  });

  it("moves a card into a custom column via the select without changing its real status", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: PLANNER_TASKS, total: 1, limit: 100, offset: 0 }),
      "GET /tasks/preferences": () => ({
        list_columns: null,
        planner_columns: ["new", "custom:x"],
        planner_positions: null,
        planner_custom_columns: { "custom:x": { title: "Ждём клиента" } },
        planner_custom_members: null,
        deadline_columns: null,
        deadline_positions: null,
        deadline_custom_columns: null,
        deadline_custom_members: null,
        filters: null,
      }),
    });
    renderApp("/tasks");
    await openPlanner();
    await screen.findByText("Собрать документы");

    change(screen.getByLabelText("Переместить «Собрать документы»"), "custom:x");

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      planner_custom_members: { "1": "custom:x" },
    });
    expect(api.count("POST", "/tasks/1/status")).toBe(0);
  });

  it("moving a card from a custom column back to a system column changes its status and clears the placement", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: PLANNER_TASKS, total: 1, limit: 100, offset: 0 }),
      "GET /tasks/preferences": () => ({
        list_columns: null,
        planner_columns: ["new", "in_progress", "custom:x"],
        planner_positions: null,
        planner_custom_columns: { "custom:x": { title: "Ждём клиента" } },
        planner_custom_members: { "1": "custom:x" },
        deadline_columns: null,
        deadline_positions: null,
        deadline_custom_columns: null,
        deadline_custom_members: null,
        filters: null,
      }),
      "POST /tasks/1/status": () => ({ ...PLANNER_TASKS[0], status: "in_progress", version: 2 }),
    });
    renderApp("/tasks");
    await openPlanner();
    const custom = await columnOf("Ждём клиента");
    within(custom).getByText("Собрать документы");

    change(within(custom).getByLabelText("Переместить «Собрать документы»"), "in_progress");

    await waitFor(() => expect(api.count("POST", "/tasks/1/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks/1/status")?.body).toEqual({
      to_status: "in_progress",
      comment: "",
      version: 1,
    });
    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      planner_custom_members: {},
    });
  });
});
