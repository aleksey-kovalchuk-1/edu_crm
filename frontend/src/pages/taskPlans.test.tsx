import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const change = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });
const sectionOf = async (heading: string) =>
  (await screen.findByRole("heading", { name: heading })).closest("section") as HTMLElement;

const PREVIEW = {
  template_id: 1,
  template_name: "Адаптация нового вуза",
  steps: [
    {
      step_id: 101,
      title: "Собрать документы",
      description: "",
      assignee: { id: 5, full_name: "Анна Демо" },
      assignee_issue: null,
      planned_start: "2026-09-01",
      deadline: "2026-09-04",
      priority: "normal",
      approval_required: false,
      is_optional: false,
      depends_on_step_id: null,
      checklist_items: [],
    },
    {
      step_id: 102,
      title: "Подписать договор",
      description: "",
      assignee: null,
      assignee_issue: "Не назначен менеджер вуза",
      planned_start: "2026-09-04",
      deadline: "2026-09-06",
      priority: "high",
      approval_required: true,
      is_optional: false,
      depends_on_step_id: 101,
      checklist_items: [],
    },
  ],
};

describe("task plans: progress on the university page", () => {
  it("lists plan runs with their progress", async () => {
    mockApi();
    renderApp("/universities/1");
    const section = await sectionOf("Планы задач");
    expect(await within(section).findByText("Адаптация нового вуза")).toBeTruthy();
    expect(within(section).getByText(/1\/4 задач/)).toBeTruthy();
    expect(within(section).getByText(/заблокировано: 1/)).toBeTruthy();
  });
});

describe("task plans: start wizard", () => {
  it("previews a plan and blocks generation until every step has an assignee", async () => {
    const api = mockApi({
      "POST /task-plan-templates/1/preview": () => PREVIEW,
    });
    renderApp("/universities/1");
    const section = await sectionOf("Планы задач");
    fireEvent.click(within(section).getByRole("button", { name: "Запустить план" }));

    await screen.findByRole("option", { name: "Адаптация нового вуза" });
    change(screen.getByLabelText("Шаблон плана"), "1");
    change(screen.getByLabelText("Дата старта"), "2026-09-01");
    fireEvent.click(screen.getByRole("button", { name: "Предпросмотр" }));

    await waitFor(() => expect(api.count("POST", "/task-plan-templates/1/preview")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/task-plan-templates/1/preview")?.body).toEqual({
      university_id: 1,
      launch_id: null,
      start_date: "2026-09-01",
    });

    expect(await screen.findByText("Собрать документы")).toBeTruthy();
    expect(screen.getByText("Подписать договор")).toBeTruthy();
    const generateButton = () => screen.getByRole("button", { name: "Создать задачи" }) as HTMLButtonElement;
    expect(generateButton().disabled).toBe(true);

    await screen.findByRole("option", { name: "Олег Кузнецов" });
    change(screen.getByLabelText("Не назначен менеджер вуза"), "6");
    expect(generateButton().disabled).toBe(false);
  });

  it("generates tasks with the chosen overrides and closes the wizard", async () => {
    const api = mockApi({
      "POST /task-plan-templates/1/preview": () => PREVIEW,
      "POST /task-plan-templates/1/generate": () => [201, { run_id: 900, tasks: [] }],
    });
    renderApp("/universities/1");
    const section = await sectionOf("Планы задач");
    fireEvent.click(within(section).getByRole("button", { name: "Запустить план" }));
    await screen.findByRole("option", { name: "Адаптация нового вуза" });
    change(screen.getByLabelText("Шаблон плана"), "1");
    change(screen.getByLabelText("Дата старта"), "2026-09-01");
    fireEvent.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await screen.findByText("Собрать документы");
    await screen.findByRole("option", { name: "Олег Кузнецов" });
    change(screen.getByLabelText("Не назначен менеджер вуза"), "6");

    fireEvent.click(screen.getByRole("button", { name: "Создать задачи" }));

    await waitFor(() => expect(api.count("POST", "/task-plan-templates/1/generate")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/task-plan-templates/1/generate")?.body).toEqual({
      university_id: 1,
      launch_id: null,
      start_date: "2026-09-01",
      assignee_overrides: { "102": 6 },
      skip_step_ids: [],
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Создать задачи" })).toBeNull());
  });
});
