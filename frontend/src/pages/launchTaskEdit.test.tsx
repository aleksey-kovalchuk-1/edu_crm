import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Task } from "../api/tasks";
import { apiError, mockApi, renderApp, sessionFixture } from "../test/utils";

/** The interaction's tasks by stage; the title follows the task so a saved rename shows up in the list. */
function launchTasks(title: () => string) {
  return () => ({
    current_category: 1,
    categories: [
      { index: 0, name: "Первый контакт", tasks: [], unfinished_count: 0 },
      {
        index: 1,
        name: "Документы",
        tasks: [
          { id: 1, title: title(), status: "new", priority: "normal", deadline: "2026-09-20", assignee: { id: 5, full_name: "Анна Демо" }, is_optional: false },
        ],
        unfinished_count: 0,
      },
    ],
    uncategorized: [],
  });
}

async function openLaunch() {
  renderApp("/interactions/1");
  await screen.findByRole("heading", { level: 2, name: "Аналитика данных" });
}

async function openRowEditor() {
  fireEvent.click(await screen.findByRole("button", { name: "Изменить задачу «Согласовать договор»" }));
  const dialog = await screen.findByRole("dialog", { name: "Изменить задачу" });
  await within(dialog).findByDisplayValue("Согласовать договор");
  return dialog;
}

describe("interaction detail: editing a task from its stage", () => {
  it("saves a new title, deadline, status and people from the row's «Изменить», then refreshes the stage list", async () => {
    let title = "Согласовать договор";
    let current: Partial<Task> = {};
    const api = mockApi({
      "GET /launches/1/tasks": launchTasks(() => title),
      "GET /tasks/1": () => ({ ...api.data.task, observers: [{ id: 9, full_name: "Наблюдатель" }], ...current }),
      "PATCH /tasks/1": (call) => {
        const body = call.body as { title: string };
        title = body.title;
        current = { ...current, ...(call.body as object), version: 2 };
        return { ...api.data.task, ...current };
      },
      "PUT /tasks/1/members": () => {
        current = { ...current, version: 3 };
        return { ...api.data.task, ...current };
      },
      "POST /tasks/1/status": () => ({ ...api.data.task, ...current, status: "in_progress", version: 4 }),
    });
    await openLaunch();
    const dialog = await openRowEditor();

    fireEvent.change(within(dialog).getByLabelText("Название"), { target: { value: "Согласовать договор с ВАДО" } });
    fireEvent.change(within(dialog).getByLabelText("Срок"), { target: { value: "2026-10-01" } });
    fireEvent.change(within(dialog).getByLabelText("Статус"), { target: { value: "in_progress" } });
    fireEvent.click(within(within(dialog).getByRole("group", { name: "Участники" })).getByLabelText("Олег Кузнецов"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(api.count("POST", "/tasks/1/status")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      version: 1, title: "Согласовать договор с ВАДО", deadline: "2026-10-01",
    });
    // Observers aren't in the dialog; the full replace must keep them.
    expect(api.calls.find((c) => c.method === "PUT" && c.path === "/tasks/1/members")?.body).toEqual({
      assignee_ids: [5], participant_ids: [6], observer_ids: [9],
    });
    // Each step uses the version the previous one returned.
    expect(api.calls.find((c) => c.path === "/tasks/1/status")?.body).toEqual({
      to_status: "in_progress", comment: "", version: 3,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByRole("link", { name: "Согласовать договор с ВАДО" })).toBeTruthy();
  });

  it("offers «Изменить задачу» next to «Создать задачу», choosing the task from this interaction's stages", async () => {
    mockApi({ "GET /launches/1/tasks": launchTasks(() => "Согласовать договор") });
    await openLaunch();
    const create = await screen.findByRole("button", { name: "Создать задачу" });
    const edit = await screen.findByRole("button", { name: "Изменить задачу" });
    expect(create.parentElement).toBe(edit.parentElement);
    await waitFor(() => expect((edit as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(edit);
    const dialog = await screen.findByRole("dialog", { name: "Изменить задачу" });
    const picker = within(dialog).getByLabelText("Задача") as HTMLSelectElement;
    expect(picker.querySelector('optgroup[label="Документы"] option[value="1"]')?.textContent).toBe("Согласовать договор");
    expect(within(dialog).queryByLabelText("Название")).toBeNull();

    fireEvent.change(picker, { target: { value: "1" } });
    expect(await within(dialog).findByDisplayValue("Согласовать договор")).toBeTruthy();
  });

  it("keeps «Изменить задачу» disabled while the interaction has no tasks", async () => {
    mockApi({
      "GET /launches/1/tasks": () => ({ current_category: 0, categories: [{ index: 0, name: "Первый контакт", tasks: [], unfinished_count: 0 }], uncategorized: [] }),
    });
    await openLaunch();
    await screen.findByText("Нет задач");
    expect((screen.getByRole("button", { name: "Изменить задачу" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("sends only what changed", async () => {
    const api = mockApi({
      "GET /launches/1/tasks": launchTasks(() => "Согласовать договор"),
      "PATCH /tasks/1": () => ({ ...api.data.task, title: "Новое название", version: 2 }),
    });
    await openLaunch();
    const dialog = await openRowEditor();
    fireEvent.change(within(dialog).getByLabelText("Название"), { target: { value: "Новое название" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ version: 1, title: "Новое название" });
    expect(api.count("PUT", "/tasks/1/members")).toBe(0);
    expect(api.count("POST", "/tasks/1/status")).toBe(0);
  });

  it("doesn't offer to clear a deadline the server can't clear", async () => {
    mockApi({ "GET /launches/1/tasks": launchTasks(() => "Согласовать договор") });
    await openLaunch();
    const dialog = await openRowEditor();
    // PATCH /tasks/{id} ignores a null deadline, so an emptied field would look saved but change nothing.
    expect((within(dialog).getByLabelText("Срок") as HTMLInputElement).required).toBe(true);
  });

  it("asks for a reason when returning a task for rework", async () => {
    const api = mockApi({
      "GET /launches/1/tasks": launchTasks(() => "Согласовать договор"),
      "GET /tasks/1": () => ({ ...api.data.task, status: "awaiting_review" }),
      "POST /tasks/1/status": () => ({ ...api.data.task, status: "in_progress", version: 2 }),
    });
    await openLaunch();
    const dialog = await openRowEditor();
    expect(within(dialog).queryByLabelText("Что нужно исправить")).toBeNull();
    fireEvent.change(within(dialog).getByLabelText("Статус"), { target: { value: "in_progress" } });
    const reason = within(dialog).getByLabelText("Что нужно исправить") as HTMLTextAreaElement;
    expect(reason.required).toBe(true);
    fireEvent.change(reason, { target: { value: "Нет подписи" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(api.count("POST", "/tasks/1/status")).toBe(1));
    expect(api.calls.find((c) => c.path === "/tasks/1/status")?.body).toEqual({
      to_status: "in_progress", comment: "Нет подписи", version: 1,
    });
  });

  it("lets a KAM who isn't the task's author change only the status", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"], undefined, { id: 5 }),
      "GET /launches/1/tasks": launchTasks(() => "Согласовать договор"),
      "GET /tasks/1": () => ({
        id: 1, title: "Согласовать договор", description: "", status: "new", priority: "normal", deadline: "2026-09-20",
        planned_start: null, creator: { id: 8, full_name: "Ирина Петрова" }, university: null, interaction: null, contract: null,
        assignees: [{ id: 5, full_name: "Анна Демо" }], participants: [], observers: [], approval_required: false,
        require_checklist_complete: false, checklist: [], parent: null, subtasks: { total: 0, completed: 0 },
        created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-01T10:00:00Z", version: 1,
      }),
    });
    await openLaunch();
    const dialog = await openRowEditor();
    expect((within(dialog).getByLabelText("Название") as HTMLInputElement).disabled).toBe(true);
    expect((within(dialog).getByLabelText("Срок") as HTMLInputElement).disabled).toBe(true);
    expect((within(dialog).getByRole("group", { name: "Исполнители" }) as HTMLFieldSetElement).disabled).toBe(true);
    const status = within(dialog).getByLabelText("Статус") as HTMLSelectElement;
    expect(status.disabled).toBe(false);
    // As the assignee they may start or defer it; cancelling is for the author or a supervisor.
    expect([...status.options].map((o) => o.value)).toEqual(["new", "in_progress", "deferred"]);
    expect(within(dialog).getByText(/может менять автор задачи или руководитель/)).toBeTruthy();
  });

  it("locks the status for a KAM who is neither the author nor an assignee", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"], undefined, { id: 6 }),
      "GET /launches/1/tasks": launchTasks(() => "Согласовать договор"),
    });
    await openLaunch();
    const dialog = await openRowEditor();
    expect((within(dialog).getByLabelText("Статус") as HTMLSelectElement).disabled).toBe(true);
    expect(within(dialog).getByText(/Статус может менять исполнитель, автор задачи или руководитель/)).toBeTruthy();
  });

  it("offers «На проверке» only for tasks that need approval", async () => {
    const api = mockApi({
      "GET /launches/1/tasks": launchTasks(() => "Согласовать договор"),
      "GET /tasks/1": () => ({ ...api.data.task, status: "in_progress" }),
    });
    await openLaunch();
    const dialog = await openRowEditor();
    const values = [...(within(dialog).getByLabelText("Статус") as HTMLSelectElement).options].map((o) => o.value);
    expect(values).toEqual(["in_progress", "completed", "deferred", "cancelled"]);
  });

  it("keeps the dialog open with the server's message when saving fails", async () => {
    mockApi({
      "GET /launches/1/tasks": launchTasks(() => "Согласовать договор"),
      "PATCH /tasks/1": () => apiError(409, "CONFLICT", "Задача уже изменена другим пользователем; обновите страницу"),
    });
    await openLaunch();
    const dialog = await openRowEditor();
    fireEvent.change(within(dialog).getByLabelText("Название"), { target: { value: "Другое" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(await within(dialog).findByText(/обновите страницу/)).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Изменить задачу" })).toBeTruthy();
  });
});
