import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

const change = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });
const asManager = () => ({ "GET /auth/me": () => sessionFixture(["crm-user"]) });

describe("task plan templates: access", () => {
  it("hides the templates link and shows a forbidden state to a crm-user, without calling the API", async () => {
    const api = mockApi(asManager());
    renderApp("/tasks/templates");
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeTruthy();
    expect(api.count("GET", "/task-plan-templates")).toBe(0);
  });

  it("shows the templates link on the Tasks page and the editor to supervisors", async () => {
    mockApi();
    renderApp("/tasks");
    const link = await screen.findByRole("link", { name: /Шаблоны планов/ });
    expect(link.getAttribute("href")).toBe("/tasks/templates");
    fireEvent.click(link);
    expect(await screen.findByText("Адаптация нового вуза")).toBeTruthy();
  });
});

describe("task plan templates: editor", () => {
  it("creates a template with name and description only", async () => {
    const api = mockApi({
      "POST /task-plan-templates": () => [
        201,
        { id: 2, name: "Новый шаблон", description: "", is_active: true, created_at: "2026-09-19T10:00:00Z", steps: [] },
      ],
    });
    renderApp("/tasks/templates");
    await screen.findByText("Адаптация нового вуза");

    fireEvent.click(screen.getByRole("button", { name: "Создать шаблон" }));
    change(screen.getByLabelText("Название шаблона"), "Новый шаблон");
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(api.count("POST", "/task-plan-templates")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/task-plan-templates")?.body).toEqual({
      name: "Новый шаблон",
      description: "",
      steps: [],
    });
  });

  it("expands a template, lists its steps and adds a new step", async () => {
    const api = mockApi({
      "POST /task-plan-templates/1/steps": () => ({
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
          {
            id: 103,
            position: 2,
            title: "Провести вебинар",
            description: "",
            assignee_rule: "manual",
            assignee_rule_user_id: null,
            start_offset_days: 5,
            deadline_offset_days: null,
            offset_unit: "calendar",
            priority: "normal",
            approval_required: false,
            is_optional: true,
            depends_on_step_id: 102,
            checklist_items: [],
          },
        ],
      }),
    });
    renderApp("/tasks/templates");
    await screen.findByText("Адаптация нового вуза");
    fireEvent.click(screen.getByRole("button", { name: "Шаги" }));

    expect(await screen.findByText("Собрать документы")).toBeTruthy();
    expect(screen.getByText("Подписать договор")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Добавить шаг/ }));
    change(screen.getByLabelText("Название шага"), "Провести вебинар");
    fireEvent.click(screen.getByRole("button", { name: "Добавить шаг" }));

    await waitFor(() => expect(api.count("POST", "/task-plan-templates/1/steps")).toBe(1));
    const body = api.calls.find((c) => c.method === "POST" && c.path === "/task-plan-templates/1/steps")
      ?.body as Record<string, unknown>;
    expect(body.title).toBe("Провести вебинар");
    expect(body.depends_on_step_id).toBe(102);
  });

  it("reorders steps with the up/down buttons", async () => {
    const api = mockApi();
    renderApp("/tasks/templates");
    await screen.findByText("Адаптация нового вуза");
    fireEvent.click(screen.getByRole("button", { name: "Шаги" }));
    await screen.findByText("Собрать документы");

    fireEvent.click(screen.getByRole("button", { name: /Переместить «Подписать договор» выше/ }));

    await waitFor(() => expect(api.count("PUT", "/task-plan-templates/1/steps-order")).toBe(1));
    expect(
      api.calls.find((c) => c.method === "PUT" && c.path === "/task-plan-templates/1/steps-order")?.body,
    ).toEqual({ step_ids: [102, 101] });
  });

  it("deletes a step", async () => {
    const api = mockApi();
    renderApp("/tasks/templates");
    await screen.findByText("Адаптация нового вуза");
    fireEvent.click(screen.getByRole("button", { name: "Шаги" }));
    await screen.findByText("Собрать документы");

    fireEvent.click(screen.getByRole("button", { name: /Удалить «Собрать документы»/ }));

    await waitFor(() => expect(api.count("DELETE", "/task-plan-template-steps/101")).toBe(1));
  });

  it("toggles a template active/inactive", async () => {
    const api = mockApi();
    renderApp("/tasks/templates");
    await screen.findByText("Адаптация нового вуза");

    fireEvent.click(screen.getByRole("button", { name: "Деактивировать" }));

    await waitFor(() => expect(api.count("PATCH", "/task-plan-templates/1")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH" && c.path === "/task-plan-templates/1")?.body).toEqual({
      is_active: false,
    });
  });

  it("includes inactive templates only when the checkbox is checked", async () => {
    const api = mockApi();
    renderApp("/tasks/templates");
    await screen.findByText("Адаптация нового вуза");
    expect(api.count("GET", "/task-plan-templates")).toBe(1);

    fireEvent.click(screen.getByLabelText("Показать неактивные"));

    await waitFor(() => expect(api.count("GET", "/task-plan-templates?include_inactive=true")).toBe(1));
  });
});
