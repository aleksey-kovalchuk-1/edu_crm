import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TaskStatus } from "../api/tasks";
import { apiError, mockApi, renderApp } from "../test/utils";

describe("tasks: list", () => {
  it("shows the default 'mine' scope selected and lists the fixture task", async () => {
    mockApi();
    renderApp("/tasks");
    const tab = await screen.findByRole("tab", { name: "Мои задачи" });
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByRole("link", { name: "Согласовать договор" })).toBeTruthy();
  });

  it("switches scope, updates the URL and requests the new scope", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    fireEvent.click(screen.getByRole("tab", { name: "Все задачи" }));

    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "GET" && c.path.includes("scope=all"))).toBe(true),
    );
    expect(
      (await screen.findByRole("tab", { name: "Все задачи" })).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("sends the search term as a query parameter", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    fireEvent.change(screen.getByRole("textbox", { name: "Поиск" }), {
      target: { value: "договор" },
    });

    await waitFor(() =>
      expect(
        api.calls.some((c) => c.method === "GET" && c.path.includes("search=%D0%B4%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80")),
      ).toBe(true),
    );
  });

  it("pages through results with the pagination controls", async () => {
    const api = mockApi({
      "GET /tasks": () => ({
        items: api.data.tasks,
        total: 30,
        limit: 25,
        offset: 0,
      }),
    });
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });
    const next = screen.getByRole("button", { name: /Вперёд/ });
    expect((screen.getByRole("button", { name: /Назад/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(next);

    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "GET" && c.path.includes("offset=25"))).toBe(true),
    );
  });
});

describe("tasks: create", () => {
  it("only sends the links and priority actually chosen", async () => {
    const api = mockApi({
      "POST /tasks": (call) => [201, { ...api.data.task, id: 5, ...(call.body as object) }],
      "GET /tasks/5": () => ({ ...api.data.task, id: 5, title: "Без вуза" }),
    });
    renderApp("/tasks");
    fireEvent.click(await screen.findByRole("button", { name: /Создать задачу/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новая задача" });
    fireEvent.change(within(dialog).getByPlaceholderText("Например, собрать документы"), {
      target: { value: "Без вуза" },
    });
    fireEvent.submit(dialog.querySelector("form")!);

    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({
      title: "Без вуза",
      priority: "normal",
      university_id: null,
      launch_id: null,
      contract_id: null,
      assignee_ids: [],
    });
  });
});

describe("tasks: detail", () => {
  it("opens the same task from a direct deep link", async () => {
    mockApi();
    renderApp("/tasks/1");
    expect(await screen.findByRole("heading", { level: 2, name: "Согласовать договор" })).toBeTruthy();
    expect(screen.getByText("Новая")).toBeTruthy();
  });

  it("shows a not-found panel for a missing or out-of-scope task, not a bare error", async () => {
    mockApi({
      "GET /tasks/999": () => apiError(404, "RECORD_NOT_FOUND", "Запись не найдена"),
    });
    renderApp("/tasks/999");
    expect(await screen.findByRole("heading", { name: "Задача не найдена" })).toBeTruthy();
    expect(await screen.findByRole("link", { name: "К списку задач" })).toBeTruthy();
  });

  it("saves an edit through the detail page", async () => {
    const api = mockApi({
      "PATCH /tasks/1": (call) => {
        api.data.task = { ...api.data.task, ...(call.body as object) };
        return api.data.task;
      },
      "GET /tasks/1": () => api.data.task,
    });
    renderApp("/tasks/1");
    fireEvent.click(await screen.findByRole("button", { name: "Изменить" }));
    const title = await screen.findByRole("textbox", { name: "Название" });
    fireEvent.change(title, { target: { value: "Согласовать договор (v2)" } });
    fireEvent.submit(title.closest("form")!);

    await waitFor(() => expect(api.count("PATCH", "/tasks/1")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      version: 1,
      title: "Согласовать договор (v2)",
    });
    expect(await screen.findByRole("heading", { level: 2, name: "Согласовать договор (v2)" })).toBeTruthy();
  });
});

describe("tasks: status workflow", () => {
  it("changes status via the status action buttons", async () => {
    const api = mockApi({
      "POST /tasks/1/status": (call) => {
        const body = call.body as { to_status: TaskStatus };
        api.data.task = { ...api.data.task, status: body.to_status, version: api.data.task.version + 1 };
        return api.data.task;
      },
      "GET /tasks/1": () => api.data.task,
    });
    renderApp("/tasks/1");
    fireEvent.click(await screen.findByRole("button", { name: "Начать" }));

    await waitFor(() => expect(api.count("POST", "/tasks/1/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks/1/status")?.body).toEqual({
      to_status: "in_progress",
      comment: "",
      version: 1,
    });
    expect(await screen.findByText("В работе")).toBeTruthy();
  });

  it("requires a comment before returning a task to in_progress from review", async () => {
    const api = mockApi({
      "GET /tasks/1": () => ({ ...api.data.task, status: "awaiting_review" }),
      "POST /tasks/1/status": (call) => ({ ...api.data.task, ...(call.body as object) }),
    });
    renderApp("/tasks/1");
    fireEvent.click(await screen.findByRole("button", { name: "Вернуть на доработку" }));
    const dialog = await screen.findByRole("dialog", { name: "Вернуть на доработку" });
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Нужно поправить формулировку" } });
    fireEvent.submit(dialog.querySelector("form")!);

    await waitFor(() => expect(api.count("POST", "/tasks/1/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({
      to_status: "in_progress",
      comment: "Нужно поправить формулировку",
    });
  });
});

describe("tasks: checklist", () => {
  it("adds a checklist item and marks it done", async () => {
    const api = mockApi({
      "POST /tasks/1/checklist-items": (call) => {
        const body = call.body as { title: string };
        const item = {
          id: 50, title: body.title, position: 0, is_done: false,
          assignee: null, deadline: null, completed_by: null, completed_at: null,
        };
        api.data.task = { ...api.data.task, checklist: [item] };
        return [201, item];
      },
      "GET /tasks/1": () => api.data.task,
      "PATCH /checklist-items/50": () => {
        const item = { ...api.data.task.checklist[0], is_done: true };
        api.data.task = { ...api.data.task, checklist: [item] };
        return item;
      },
    });
    renderApp("/tasks/1");
    const input = await screen.findByRole("textbox", { name: "Название пункта чек-листа" });
    fireEvent.change(input, { target: { value: "Проверить документы" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(api.count("POST", "/tasks/1/checklist-items")).toBe(1));

    const checkbox = await screen.findByRole("checkbox", { name: "Проверить документы" });
    fireEvent.click(checkbox);
    await waitFor(() => expect(api.count("PATCH", "/checklist-items/50")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_done: true });
  });
});

describe("tasks: comments", () => {
  it("posts a comment", async () => {
    const api = mockApi({
      "POST /tasks/1/comments": () => [
        201,
        { id: 1, author: { id: 5, full_name: "Ирина Петрова" }, body: "Всё готово", created_at: "2026-09-19T10:00:00Z", attachments: [] },
      ],
    });
    renderApp("/tasks/1");
    const textarea = await screen.findByPlaceholderText("Написать комментарий…");
    fireEvent.change(textarea, { target: { value: "Всё готово" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить" }));

    await waitFor(() => expect(api.count("POST", "/tasks/1/comments")).toBe(1));
  });
});

describe("tasks: counters and filters", () => {
  it("shows counters and applies a filter when a tile is clicked", async () => {
    const api = mockApi({
      "GET /tasks/counters": () => ({ open: 3, overdue: 2, due_today: 1, awaiting_review: 0, no_deadline: 1 }),
    });
    renderApp("/tasks");
    const overdueTile = (await screen.findByText("2")).closest("button")!;
    expect(within(overdueTile).getByText("Просрочено")).toBeTruthy();
    fireEvent.click(overdueTile);

    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "GET" && c.path.includes("deadline_preset=overdue"))).toBe(true),
    );
  });

  it("adding a status filter shows a removable chip and requests it; removing it clears the request", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    fireEvent.click(screen.getByRole("checkbox", { name: "Завершена" }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "GET" && c.path.includes("status=completed"))).toBe(true),
    );
    const chip = await screen.findByRole("button", { name: /Статус: Завершена/ });

    fireEvent.click(chip);
    await waitFor(() =>
      expect(
        api.calls.filter((c) => c.method === "GET" && c.path.includes("status=completed")).length,
      ).toBe(1), // no further request carries the removed filter
    );
    expect(screen.queryByRole("button", { name: /Статус: Завершена/ })).toBeNull();
  });
});

describe("tasks: deadline view", () => {
  it("switches to the Deadlines view and renders groups", async () => {
    mockApi({
      "GET /tasks/deadline-groups": () => [
        { group: "overdue", total: 1, items: [{ id: 1, title: "Согласовать договор", status: "new", priority: "normal", deadline: "2026-09-01", creator: null, assignees: [], university: null, created_at: "2026-09-01T00:00:00Z" }] },
        { group: "today", total: 0, items: [] },
        { group: "this_week", total: 0, items: [] },
        { group: "next_week", total: 0, items: [] },
        { group: "later", total: 0, items: [] },
        { group: "no_deadline", total: 0, items: [] },
        { group: "completed", total: 0, items: [] },
      ],
    });
    renderApp("/tasks");
    fireEvent.click(await screen.findByRole("tab", { name: "Сроки" }));
    expect(await screen.findByRole("heading", { name: /Просрочено/ })).toBeTruthy();
    expect(await screen.findByRole("link", { name: /Согласовать договор/ })).toBeTruthy();
  });
});

describe("tasks: bulk actions", () => {
  it("selects rows and applies a bulk status change, reporting per-task skips", async () => {
    const api = mockApi({
      "POST /tasks/bulk/status": () => ({ updated: [1], skipped: [{ id: 2, reason: "Недостаточно прав для этого действия" }] }),
    });
    renderApp("/tasks");
    const row = (await screen.findByRole("link", { name: "Согласовать договор" })).closest("tr")!;
    fireEvent.click(within(row).getByRole("checkbox"));
    const select = await screen.findByLabelText("Статус", { selector: "select" });
    fireEvent.change(select, { target: { value: "in_progress" } });

    await waitFor(() => expect(api.count("POST", "/tasks/bulk/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks/bulk/status")?.body).toMatchObject({
      task_ids: [1],
      to_status: "in_progress",
    });
    expect(await screen.findByText(/Не удалось изменить 1 из 2/)).toBeTruthy();
  });

  it("requires confirmation before archiving selected tasks", async () => {
    const api = mockApi({
      "POST /tasks/bulk/archive": () => ({ updated: [1], skipped: [] }),
    });
    renderApp("/tasks");
    const row = (await screen.findByRole("link", { name: "Согласовать договор" })).closest("tr")!;
    fireEvent.click(within(row).getByRole("checkbox"));
    fireEvent.click(await screen.findByRole("button", { name: "Архивировать" }));
    const dialog = await screen.findByRole("dialog", { name: "Архивировать задачи" });
    expect(api.count("POST", "/tasks/bulk/archive")).toBe(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "Архивировать" }));
    await waitFor(() => expect(api.count("POST", "/tasks/bulk/archive")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks/bulk/archive")?.body).toEqual({
      task_ids: [1],
      confirm: true,
    });
  });
});

describe("tasks: configurable columns", () => {
  it("toggling a column saves preferences", async () => {
    const api = mockApi({
      "PUT /tasks/preferences": (call) => ({ list_columns: (call.body as { list_columns: string[] }).list_columns, planner_columns: null, planner_positions: null }),
    });
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });
    fireEvent.click(screen.getByText("Колонки"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Дата создания" }));

    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      list_columns: expect.arrayContaining(["created_at"]),
    });
  });
});
