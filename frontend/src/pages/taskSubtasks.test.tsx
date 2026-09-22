import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

const SUBTASK = {
  id: 20,
  title: "Собрать данные",
  status: "new",
  priority: "normal",
  deadline: null,
  creator: { id: 1, full_name: "Анна Петрова" },
  assignees: [{ id: 5, full_name: "Анна Демо" }],
  university: null,
  created_at: "2026-09-01T10:00:00Z",
  version: 1,
};

const subtasksSection = async () => (await screen.findByText("Подзадачи")).closest(".task-subtasks") as HTMLElement;

describe("task subtasks: creation with an assignee", () => {
  it("shows a responsible-user selector in the add row and creates the subtask with it", async () => {
    const api = mockApi({
      "POST /tasks": () => [201, { ...SUBTASK, id: 21 }],
    });
    renderApp("/tasks/1");
    const section = await subtasksSection();
    const title = within(section).getByLabelText("Название подзадачи");
    fireEvent.change(title, { target: { value: "Новая подзадача" } });
    fireEvent.change(within(section).getByLabelText("Ответственный", { selector: "select" }), { target: { value: "6" } });
    fireEvent.click(within(section).getByRole("button", { name: "Добавить" }));

    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks")?.body).toMatchObject({
      title: "Новая подзадача",
      parent_task_id: 1,
      assignee_ids: [6],
    });
  });

  it("creates the subtask with no assignee when none is chosen", async () => {
    const api = mockApi({ "POST /tasks": () => [201, { ...SUBTASK, id: 22 }] });
    renderApp("/tasks/1");
    const section = await subtasksSection();
    fireEvent.change(within(section).getByLabelText("Название подзадачи"), { target: { value: "Без исполнителя" } });
    fireEvent.click(within(section).getByRole("button", { name: "Добавить" }));

    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/tasks")?.body).toMatchObject({
      assignee_ids: [],
    });
  });
});

describe("task subtasks: existing rows", () => {
  it("shows title, status, and the responsible user, defaulting to «Без исполнителя»", async () => {
    mockApi({
      "GET /tasks/1/subtasks": () => [SUBTASK, { ...SUBTASK, id: 23, title: "Без ответственного", assignees: [] }],
    });
    renderApp("/tasks/1");
    const section = await subtasksSection();
    expect(await within(section).findByRole("link", { name: "Собрать данные" })).toBeTruthy();
    expect(within(section).getByRole("link", { name: "Без ответственного" })).toBeTruthy();
  });

  it("lets a supervisor reassign a subtask via a select, sending only assignee_ids", async () => {
    const api = mockApi({
      "GET /tasks/1/subtasks": () => [SUBTASK],
      "PATCH /tasks/20/assignees": () => ({ ...SUBTASK, assignees: [{ id: 6, full_name: "Олег Кузнецов" }] }),
    });
    renderApp("/tasks/1");
    const section = await subtasksSection();
    await within(section).findByRole("link", { name: "Собрать данные" });

    const select = within(section).getByLabelText("Ответственный за «Собрать данные»");
    fireEvent.change(select, { target: { value: "6" } });

    await waitFor(() => expect(api.count("PATCH", "/tasks/20/assignees")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH" && c.path === "/tasks/20/assignees")?.body).toEqual({
      assignee_ids: [6],
    });
  });

  it("shows read-only text (no select) for a user without reassignment rights", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"]),
      "GET /tasks/1/subtasks": () => [{ ...SUBTASK, creator: { id: 99, full_name: "Кто-то другой" } }],
    });
    renderApp("/tasks/1");
    const section = await subtasksSection();
    await within(section).findByRole("link", { name: "Собрать данные" });
    const list = section.querySelector(".subtask-list") as HTMLElement;
    expect(within(list).getByText("Анна Демо")).toBeTruthy();
    expect(within(section).queryByLabelText("Ответственный за «Собрать данные»")).toBeNull();
  });
});
