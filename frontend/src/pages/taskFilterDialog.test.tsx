import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

const location = () => screen.getByTestId("location").textContent ?? "";
const scopeSelect = () => screen.getByRole("combobox", { name: "Область видимости" }) as HTMLSelectElement;
const openDialog = async () => {
  fireEvent.click(await screen.findByRole("button", { name: /Фильтры/ }));
  return screen.findByRole("dialog", { name: "Фильтры задач" });
};

describe("tasks: visible scopes", () => {
  it("offers only the five required scopes, in order, and hides the other two", async () => {
    mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    const options = within(scopeSelect()).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Мои задачи", "Назначено мне", "Я участвую", "Задачи команды", "Все задачи"]);
    expect(screen.queryByRole("tablist", { name: "Область видимости" })).toBeNull();
  });

  it("falls back to 'mine' for an old scope=created or scope=observing URL instead of crashing", async () => {
    const api = mockApi();
    renderApp("/tasks?scope=created");
    expect(await screen.findByRole("link", { name: "Согласовать договор" })).toBeTruthy();
    expect(scopeSelect().value).toBe("mine");
    await waitFor(() => expect(api.calls.some((c) => c.method === "GET" && c.path.includes("scope=mine"))).toBe(true));
    expect(api.calls.some((c) => c.method === "GET" && c.path.includes("scope=created"))).toBe(false);

    renderApp("/tasks?scope=observing");
    const selects = await screen.findAllByRole("combobox", { name: "Область видимости" });
    expect((selects.at(-1) as HTMLSelectElement).value).toBe("mine");
  });
});

describe("tasks: filter dialog visibility", () => {
  it("does not render the filter form until the Фильтры button is clicked", async () => {
    mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    expect(screen.queryByRole("dialog", { name: "Фильтры задач" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Статус" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Приоритет" })).toBeNull();
  });

  it("opens the dialog from the Фильтры button, showing the current scope as supporting text", async () => {
    mockApi();
    renderApp("/tasks");
    const dialog = await openDialog();
    expect(within(dialog).getByText(/Мои задачи/)).toBeTruthy();
    expect(within(dialog).getByRole("group", { name: "Статус" })).toBeTruthy();
    expect(within(dialog).getByRole("group", { name: "Приоритет" })).toBeTruthy();
  });

  it("is visible in both the List and Deadlines views", async () => {
    mockApi();
    renderApp("/tasks");
    await screen.findByRole("button", { name: /Фильтры/ });
    fireEvent.click(await screen.findByRole("tab", { name: "Сроки" }));
    expect(await screen.findByRole("button", { name: /Фильтры/ })).toBeTruthy();
  });
});

describe("tasks: cancel discards the draft", () => {
  it("editing a filter then pressing Отмена changes nothing", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });
    const callsBefore = api.calls.length;

    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Завершена" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));

    expect(screen.queryByRole("dialog", { name: "Фильтры задач" })).toBeNull();
    expect(location()).not.toContain("status=");
    expect(api.count("PUT", "/tasks/preferences")).toBe(0);
    expect(api.calls.slice(callsBefore).some((c) => c.path.includes("status=completed"))).toBe(false);
    expect(screen.queryByRole("button", { name: /Статус: Завершена/ })).toBeNull();
  });

  it("closing with Escape behaves exactly like Отмена", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Высокий" }));
    fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Фильтры задач" })).toBeNull());
    expect(location()).not.toContain("priority=");
    expect(api.count("PUT", "/tasks/preferences")).toBe(0);
  });

  it("returns keyboard focus to the Фильтры button after closing", async () => {
    mockApi();
    renderApp("/tasks");
    const filterButton = await screen.findByRole("button", { name: /Фильтры/ });
    fireEvent.click(filterButton);
    const dialog = await screen.findByRole("dialog", { name: "Фильтры задач" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));

    await waitFor(() => expect(document.activeElement).toBe(filterButton));
  });
});

describe("tasks: save applies and persists", () => {
  it("Сохранить applies the draft, updates the URL, requests it and persists it, then closes", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Завершена" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    expect(screen.queryByRole("dialog", { name: "Фильтры задач" })).toBeNull();
    expect(location()).toContain("status=completed");
    await waitFor(() => expect(api.calls.some((c) => c.method === "GET" && c.path.includes("status=completed"))).toBe(true));
    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT" && c.path === "/tasks/preferences")?.body).toEqual({
      filters: {
        "list:mine": {
          status: ["completed"], priority: [], university_id: undefined, assignee_id: undefined, creator_id: undefined,
          deadline_preset: undefined, active: undefined, has_checklist: undefined,
        },
      },
    });
  });

  it("shows the correct active-filter count badge and a compact removable chip summary", async () => {
    mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });
    expect(screen.queryByLabelText(/Применено фильтров/)).toBeNull();

    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Завершена" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Высокий" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByLabelText("Применено фильтров: 2")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Статус: Завершена/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Приоритет: Высокий/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Сбросить все" })).toBeTruthy();
  });
});

describe("tasks: saved filters restore per view/scope, without leaking", () => {
  it("restores a scope's saved filters on arrival, and does not leak into another scope or view", async () => {
    mockApi({
      "GET /tasks/preferences": () => ({
        list_columns: null,
        planner_columns: null,
        planner_positions: null,
        filters: {
          "list:mine": { status: ["completed"] },
          "deadlines:mine": { deadline_preset: "overdue" },
          "list:all": { priority: ["high"] },
        },
      }),
    });
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });
    await waitFor(() => expect(location()).toContain("status=completed"));
    expect(location()).not.toContain("deadline_preset");
    expect(location()).not.toContain("priority=");

    fireEvent.click(await screen.findByRole("tab", { name: "Сроки" }));
    await waitFor(() => expect(location()).toContain("deadline_preset=overdue"));
    expect(location()).not.toContain("status=completed");

    fireEvent.click(await screen.findByRole("tab", { name: "Список" }));
    fireEvent.change(scopeSelect(), { target: { value: "all" } });
    await waitFor(() => expect(location()).toContain("priority=high"));
    expect(location()).not.toContain("status=completed");
  });

  it("an explicit URL filter takes precedence over a saved one", async () => {
    mockApi({
      "GET /tasks/preferences": () => ({
        list_columns: null,
        planner_columns: null,
        planner_positions: null,
        filters: { "list:mine": { status: ["completed"] } },
      }),
    });
    renderApp("/tasks?status=new");
    await screen.findByRole("link", { name: "Согласовать договор" });
    expect(location()).toContain("status=new");
    expect(location()).not.toContain("status=completed");
  });
});

describe("tasks: permissions unaffected", () => {
  it("a plain crm-user can still pick every visible scope", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });
    for (const name of ["Назначено мне", "Я участвую", "Задачи команды", "Все задачи", "Мои задачи"]) {
      expect(within(scopeSelect()).getByRole("option", { name })).toBeTruthy();
    }
  });
});

describe("tasks: filter panel fields", () => {
  it("offers who does / who set the task, and no longer the checklist or activity filters", async () => {
    mockApi();
    renderApp("/tasks");
    const dialog = await openDialog();
    expect(within(dialog).getByRole("combobox", { name: "Исполнитель" })).toBeTruthy();
    expect(within(dialog).getByRole("combobox", { name: "Постановщик" })).toBeTruthy();
    expect(within(dialog).getByRole("combobox", { name: "Срок" })).toBeTruthy();
    expect(within(dialog).queryByRole("combobox", { name: "Чек-лист" })).toBeNull();
    expect(within(dialog).queryByRole("combobox", { name: "Активность" })).toBeNull();
  });

  it("filters by assignee, shows it as a named chip and saves it with the preset", async () => {
    const api = mockApi();
    renderApp("/tasks");
    await screen.findByRole("link", { name: "Согласовать договор" });

    const dialog = await openDialog();
    const assignee = within(dialog).getByRole("combobox", { name: "Исполнитель" });
    await within(assignee).findByRole("option", { name: "Олег Кузнецов" });
    fireEvent.change(assignee, { target: { value: "6" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(api.calls.some((c) => c.method === "GET" && c.path.includes("assignee_id=6"))).toBe(true));
    expect(await screen.findByRole("button", { name: /Исполнитель: Олег Кузнецов/ })).toBeTruthy();
    await waitFor(() => expect(api.count("PUT", "/tasks/preferences")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toMatchObject({ filters: { "list:mine": { assignee_id: 6 } } });
  });
});
