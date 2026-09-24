import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { prefillDateForColumn } from "../components/tasks/deadlineBoard";
import { mockApi, renderApp, LIST_ITEM_DEFAULTS } from "../test/utils";

const change = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });

async function openDeadlines() {
  fireEvent.click(await screen.findByRole("tab", { name: "Сроки" }));
}

const columnOf = async (heading: string | RegExp) =>
  (await screen.findByRole("heading", { name: heading })).closest(".planner-column") as HTMLElement;

const OVERDUE_TASK = {
  id: 1,
  title: "Собрать документы",
  status: "new",
  priority: "urgent",
  deadline: "2020-01-01",
  creator: null,
  assignees: [{ id: 5, full_name: "Анна Демо" }],
  university: { id: 1, name: "КС" },
  created_at: "2026-09-01T10:00:00Z",
  ...LIST_ITEM_DEFAULTS,
  version: 1,
};

const NO_DEADLINE_TASK = {
  id: 2,
  title: "Без срока задача",
  status: "in_progress",
  priority: "normal",
  deadline: null,
  creator: null,
  assignees: [],
  university: null,
  created_at: "2026-09-01T10:00:00Z",
  ...LIST_ITEM_DEFAULTS,
  version: 3,
};

describe("task deadline board: columns always present", () => {
  it("shows all 6 system columns, including ones with no tasks", async () => {
    mockApi({ "GET /tasks": () => ({ items: [], total: 0, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openDeadlines();

    for (const label of ["Просрочены", "Сегодня", "На этой неделе", "На следующей неделе", "Позже", "Без срока"]) {
      expect(await screen.findByRole("heading", { name: label })).toBeTruthy();
    }
    const empty = await columnOf("Без срока");
    expect(within(empty).getByText("Пусто")).toBeTruthy();
  });

  it("buckets a clearly-overdue task and a no-deadline task into the right columns, showing card details", async () => {
    mockApi({ "GET /tasks": () => ({ items: [OVERDUE_TASK, NO_DEADLINE_TASK], total: 2, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openDeadlines();

    const overdue = await columnOf("Просрочены");
    expect(within(overdue).getByText("Собрать документы")).toBeTruthy();
    expect(within(overdue).getByText(/Срочный/)).toBeTruthy();
    expect(within(overdue).getByText("Анна Демо")).toBeTruthy();
    expect(within(overdue).getByText("КС")).toBeTruthy();

    const noDeadline = await columnOf("Без срока");
    expect(within(noDeadline).getByText("Без срока задача")).toBeTruthy();
  });
});

describe("task deadline board: search/scope/filters", () => {
  it("requests the board's tasks with the active scope, search and active=true", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: [], total: 0, limit: 100, offset: 0 }) });
    renderApp("/tasks?scope=all&q=%D0%B4%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80");
    await openDeadlines();

    await waitFor(() =>
      expect(
        api.calls.some(
          (c) =>
            c.method === "GET" &&
            c.path.startsWith("/tasks?") &&
            c.path.includes("scope=all") &&
            c.path.includes("active=true") &&
            c.path.includes("search=%D0%B4%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80"),
        ),
      ).toBe(true),
    );
  });
});

describe("task deadline board: creating from a column", () => {
  it("prefills the deadline per the column's mapping (На этой неделе -> end of this week)", async () => {
    mockApi({ "GET /tasks": () => ({ items: [], total: 0, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openDeadlines();
    const column = await columnOf("На этой неделе");

    fireEvent.click(within(column).getByRole("button", { name: "Добавить задачу" }));
    const dialog = await screen.findByRole("dialog", { name: /Новая задача/ });
    expect((within(dialog).getByLabelText("Срок") as HTMLInputElement).value).toBe(prefillDateForColumn("this_week", new Date()));
  });

  it("prefills no date for Без срока", async () => {
    mockApi({ "GET /tasks": () => ({ items: [], total: 0, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openDeadlines();
    const column = await columnOf("Без срока");

    fireEvent.click(within(column).getByRole("button", { name: "Добавить задачу" }));
    const dialog = await screen.findByRole("dialog", { name: /Новая задача/ });
    expect((within(dialog).getByLabelText("Срок") as HTMLInputElement).value).toBe("");
  });

  it("creates the task and closes the dialog", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: [], total: 0, limit: 100, offset: 0 }),
      "POST /tasks": () => [201, { ...OVERDUE_TASK, id: 99, title: "Новая" }],
    });
    renderApp("/tasks");
    await openDeadlines();
    const column = await columnOf("Сегодня");
    fireEvent.click(within(column).getByRole("button", { name: "Добавить задачу" }));
    const dialog = await screen.findByRole("dialog", { name: /Новая задача/ });
    fireEvent.change(within(dialog).getByLabelText("Название"), { target: { value: "Новая" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks")?.body).toMatchObject({
      deadline: prefillDateForColumn("today", new Date()),
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /Новая задача/ })).toBeNull());
  });
});

describe("task deadline board: moving cards between system columns", () => {
  it("moving a card into a system column updates its real deadline", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: [OVERDUE_TASK], total: 1, limit: 100, offset: 0 }),
      "PATCH /tasks/1": () => ({ ...OVERDUE_TASK, deadline: null }),
    });
    renderApp("/tasks");
    await openDeadlines();
    await screen.findByText("Собрать документы");

    change(screen.getByLabelText("Переместить «Собрать документы»"), "no_deadline");

    await waitFor(() => expect(api.count("PATCH", "/tasks/1")).toBe(1));
    const body = api.calls.find((c) => c.method === "PATCH" && c.path === "/tasks/1")?.body as { deadline: unknown; version: number };
    expect(body.deadline).toBeNull();
    expect(body.version).toBe(1);
  });

  it("shows a readable error and leaves the card in place when the update is rejected", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: [OVERDUE_TASK], total: 1, limit: 100, offset: 0 }),
      "PATCH /tasks/1": () => [403, { code: "FORBIDDEN", message: "Недостаточно прав для этого действия", details: null }],
    });
    renderApp("/tasks");
    await openDeadlines();
    const overdue = await columnOf("Просрочены");
    within(overdue).getByText("Собрать документы");

    change(screen.getByLabelText("Переместить «Собрать документы»"), "no_deadline");

    await waitFor(() => expect(api.count("PATCH", "/tasks/1")).toBe(1));
    expect(await screen.findByText(/Недостаточно прав для этого действия/)).toBeTruthy();
    const stillOverdue = await columnOf("Просрочены");
    expect(within(stillOverdue).getByText("Собрать документы")).toBeTruthy();
  });
});

describe("task deadline board: manual card order persists", () => {
  it("reorders two cards in the same column and saves the order", async () => {
    const second = { ...OVERDUE_TASK, id: 3, title: "Вторая просроченная" };
    const api = mockApi({ "GET /tasks": () => ({ items: [OVERDUE_TASK, second], total: 2, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openDeadlines();
    await screen.findByText("Собрать документы");

    fireEvent.click(screen.getByRole("button", { name: "Переместить «Собрать документы» ниже в колонке" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      deadline_positions: { overdue: [3, 1] },
    });
  });
});

describe("task deadline board: custom columns", () => {
  it("adds, and can move a card into, a custom column without changing the task's real deadline", async () => {
    const api = mockApi({ "GET /tasks": () => ({ items: [OVERDUE_TASK], total: 1, limit: 100, offset: 0 }) });
    renderApp("/tasks");
    await openDeadlines();
    await screen.findByText("Собрать документы");

    fireEvent.click(screen.getByRole("button", { name: "Добавить колонку" }));
    fireEvent.change(screen.getByLabelText("Название новой колонки"), { target: { value: "На согласовании" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));

    change(screen.getByLabelText("Переместить «Собрать документы»"), (api.calls.find((c) => c.method === "PUT")?.body as { deadline_columns: string[] }).deadline_columns.at(-1)!);

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(2));
    expect(api.count("PATCH", "/tasks/1")).toBe(0);
    expect(await screen.findByRole("heading", { name: /На согласовании/ })).toBeTruthy();
  });

  it("deletes a custom column with confirmation, returning its task to the natural column", async () => {
    const api = mockApi({
      "GET /tasks": () => ({ items: [OVERDUE_TASK], total: 1, limit: 100, offset: 0 }),
      "GET /tasks/preferences": () => ({
        list_columns: null, planner_columns: null, planner_positions: null,
        planner_custom_columns: null, planner_custom_members: null,
        deadline_columns: ["overdue", "today", "this_week", "next_week", "later", "no_deadline", "custom:x"],
        deadline_positions: null,
        deadline_custom_columns: { "custom:x": { title: "На согласовании" } },
        deadline_custom_members: { "1": "custom:x" },
        filters: null,
      }),
    });
    renderApp("/tasks");
    await openDeadlines();
    const custom = await columnOf("На согласовании");
    within(custom).getByText("Собрать документы");

    fireEvent.click(within(custom).getByRole("button", { name: "Удалить колонку «На согласовании»" }));
    const dialog = await screen.findByRole("dialog", { name: "Удалить колонку «На согласовании»?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      deadline_columns: ["overdue", "today", "this_week", "next_week", "later", "no_deadline"],
      deadline_custom_columns: {},
      deadline_custom_members: {},
    });
    expect(screen.queryByRole("heading", { name: /На согласовании/ })).toBeNull();
    const overdue = await columnOf("Просрочены");
    expect(within(overdue).getByText("Собрать документы")).toBeTruthy();
  });
});
