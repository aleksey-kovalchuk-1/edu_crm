import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  CSRF_TOKEN,
  apiError,
  deferred,
  mockApi,
  never,
  renderApp,
} from "../test/utils";

/** Board column title that currently holds the card with this code. */
const columnOf = (code: string) =>
  screen
    .getByText(code)
    .closest(".board-column")
    ?.querySelector("h2")?.textContent;

describe("routing", () => {
  it.each([
    ["/", "Всё важное — в одном месте", "Аналитика данных"],
    ["/universities", "Учебные заведения", "Колледж связи"],
    ["/interactions", "Взаимодействия", "ВЗ-0001"],
    ["/tasks", "Задачи", "Согласовать договор"],
    ["/analytics", "Аналитика", "Показатели по годам"],
  ])("renders %s", async (path, title, content) => {
    mockApi();
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeTruthy();
    expect((await screen.findAllByText(content)).length).toBeGreaterThan(0);
  });

  it("marks the current page in the sidebar", async () => {
    mockApi();
    renderApp("/tasks");
    const link = await screen.findByRole("link", { name: /Задачи/ });
    expect(link.className).toContain("active");
    expect(link.getAttribute("aria-current")).toBe("page");
  });

  it("shows a not-found page with a link home", async () => {
    mockApi();
    renderApp("/no-such-page");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Страница не найдена" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /Перейти на главную/ }).getAttribute("href"),
    ).toBe("/");
  });

  it("shows API errors with their code", async () => {
    mockApi({
      "GET /dashboard": () =>
        apiError(503, "SERVICE_UNAVAILABLE", "Сервис временно недоступен"),
    });
    renderApp("/analytics");
    // 5xx responses are retried once after 300 ms before the error shows.
    const alert = await screen.findByRole("alert", {}, { timeout: 2000 });
    expect(alert.textContent).toContain(
      "Сервис временно недоступен (код SERVICE_UNAVAILABLE)",
    );
  });
});

describe("interactions page", () => {
  it("filters by the server overdue flag without recomputing it", async () => {
    mockApi();
    renderApp("/interactions");
    await screen.findByText("ВЗ-0001");
    fireEvent.click(screen.getByRole("button", { name: /Требуют внимания/ }));
    // ВЗ-0001 has a past deadline but overdue=false; ВЗ-0002 is future but overdue=true.
    expect(screen.queryByText("ВЗ-0001")).toBeNull();
    expect(screen.getByText("ВЗ-0002")).toBeTruthy();
    expect(screen.getByText("1 записей")).toBeTruthy();
  });

  it("opens interactions filtered by the university from its card", async () => {
    mockApi();
    renderApp("/universities");
    const card = (await screen.findByText("Колледж связи")).closest("article")!;
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: /Открыть/ }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Взаимодействия" }),
    ).toBeTruthy();
    expect(((await screen.findByRole("textbox", { name: "Поиск" })) as HTMLInputElement).value).toBe(
      "Колледж связи",
    );
    expect(await screen.findByText("ВЗ-0001")).toBeTruthy();
    expect(screen.queryByText("ВЗ-0002")).toBeNull();
  });
});

describe("task toggle", () => {
  it("sends PATCH and refetches only tasks", async () => {
    const api = mockApi({
      "PATCH /tasks/1": (call) => {
        const done = (call.body as { done: boolean }).done;
        api.data.tasks = api.data.tasks.map((t) => (t.id === 1 ? { ...t, done } : t));
        return api.data.tasks[0];
      },
    });
    renderApp("/tasks");
    const checkbox = (await screen.findByRole("checkbox", {
      name: "Согласовать договор",
    })) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);

    fireEvent.click(checkbox);

    await waitFor(() => expect(checkbox.checked).toBe(true));
    await waitFor(() => expect(api.count("GET", "/tasks")).toBe(2));
    expect(api.calls.find((c) => c.method === "PATCH")).toMatchObject({
      method: "PATCH",
      path: "/tasks/1",
      body: { done: true },
      headers: { "x-csrf-token": CSRF_TOKEN },
    });
    expect(
      api.calls.filter((c) => c.method === "GET").some((c) => "x-csrf-token" in c.headers),
    ).toBe(false);
    expect(api.count("GET", "/launches")).toBe(1);
    expect(api.count("GET", "/universities")).toBe(0);
    expect(api.count("GET", "/stages")).toBe(0);
    expect(api.count("GET", "/dashboard")).toBe(0);
    await waitFor(() => expect(checkbox.disabled).toBe(false));
    expect(checkbox.checked).toBe(true);
  });

  it("rolls back the optimistic value when PATCH fails", async () => {
    const patch = deferred<unknown>();
    const api = mockApi({
      "PATCH /tasks/1": () => patch.promise,
      // Any refetch after the error hangs, so only the rollback can restore the value.
      "GET /tasks": () =>
        api.count("GET", "/tasks") > 1 ? never() : api.data.tasks,
    });
    renderApp("/tasks");
    const checkbox = (await screen.findByRole("checkbox", {
      name: "Согласовать договор",
    })) as HTMLInputElement;

    fireEvent.click(checkbox);
    await waitFor(() => expect(api.count("PATCH", "/tasks/1")).toBe(1));
    expect(checkbox.checked).toBe(true);

    patch.resolve(apiError(404, "RECORD_NOT_FOUND", "Запись не найдена"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Запись не найдена (код RECORD_NOT_FOUND)",
    );
    expect(checkbox.checked).toBe(false);
  });
});

describe("stage change", () => {
  async function openLaunchAndPickStage(stage: string) {
    await screen.findByText("ВЗ-0001");
    expect(columnOf("ВЗ-0001")).toBe("Документы");
    fireEvent.click(screen.getByRole("button", { name: /Аналитика данных/ }));
    const dialog = await screen.findByRole("dialog", { name: "Аналитика данных" });
    await within(dialog).findByRole("option", { name: "1. Этап 1" });
    fireEvent.change(within(dialog).getByRole("combobox"), {
      target: { value: stage },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить этап" }));
    return dialog;
  }

  it("moves the card optimistically, closes on success and refreshes that launch", async () => {
    const patch = deferred<unknown>();
    const api = mockApi({ "PATCH /launches/1": () => patch.promise });
    renderApp("/interactions");
    const dialog = await openLaunchAndPickStage("0");

    await waitFor(() => expect(api.count("PATCH", "/launches/1")).toBe(1));
    expect(columnOf("ВЗ-0001")).toBe("Первый контакт");
    expect(dialog.isConnected).toBe(true);

    api.data.launches = api.data.launches.map((l) => (l.id === 1 ? { ...l, stage: 0 } : l));
    patch.resolve(api.data.launches[0]);

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(api.count("GET", "/launches")).toBe(2));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ stage: 0 });
    // That launch's history is invalidated (refetched while the modal was still mounted).
    await waitFor(() => expect(api.count("GET", "/launches/1/history")).toBe(2));
    expect(api.count("GET", "/tasks")).toBe(1);
    expect(api.count("GET", "/universities")).toBe(0);
    // Dashboard is invalidated but not mounted on this page, so it is not fetched.
    expect(api.count("GET", "/dashboard")).toBe(0);
    expect(columnOf("ВЗ-0001")).toBe("Первый контакт");
  });

  it("rolls the card back and keeps the dialog open when PATCH fails", async () => {
    const patch = deferred<unknown>();
    const api = mockApi({
      "PATCH /launches/1": () => patch.promise,
      "GET /launches": () =>
        api.count("GET", "/launches") > 1 ? never() : api.data.launches,
    });
    renderApp("/interactions");
    const dialog = await openLaunchAndPickStage("0");
    await waitFor(() => expect(api.count("PATCH", "/launches/1")).toBe(1));
    expect(columnOf("ВЗ-0001")).toBe("Первый контакт");

    patch.resolve(apiError(409, "CONFLICT", "Конфликт данных"));

    expect((await within(dialog).findByRole("alert")).textContent).toBe(
      "Конфликт данных (код CONFLICT)",
    );
    expect(columnOf("ВЗ-0001")).toBe("Документы");
    expect(screen.getByRole("dialog")).toBe(dialog);
  });
});

describe("create forms", () => {
  it("maps field errors in the university form", async () => {
    mockApi({
      "POST /universities": () =>
        apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
          { field: "city", message: "Укажите город", type: "missing" },
        ]),
    });
    renderApp("/universities");
    fireEvent.click(await screen.findByRole("button", { name: /Добавить заведение/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новое учебное заведение" });
    fireEvent.change(within(dialog).getByPlaceholderText("Название учебного заведения"), {
      target: { value: "Колледж" },
    });
    fireEvent.submit(dialog.querySelector("form")!);
    const message = await within(dialog).findByText("Укажите город");
    expect(message.closest("label")?.querySelector("input")?.name).toBe("city");
    expect(within(dialog).getByRole("alert").textContent).toBe(
      "Проверьте заполненные поля (код VALIDATION_ERROR)",
    );
  });

  it("sends numbers from the launch form and maps field errors", async () => {
    const api = mockApi({
      "POST /launches": () =>
        apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
          { field: "students", message: "Слишком много обучающихся", type: "less_than_equal" },
          { field: "university_id", message: "Учебное заведение не найдено", type: "missing" },
        ]),
    });
    renderApp("/tasks");
    fireEvent.click(await screen.findByRole("button", { name: /Новое взаимодействие/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новое взаимодействие" });
    await within(dialog).findByRole("option", { name: "Технический университет" });
    const form = dialog.querySelector("form")!;
    const field = (name: string) =>
      form.querySelector(`[name="${name}"]`) as HTMLInputElement;
    fireEvent.change(field("university_id"), { target: { value: "2" } });
    fireEvent.change(field("program"), { target: { value: "Разработка на Python" } });
    fireEvent.change(field("product"), { target: { value: "Python" } });
    fireEvent.change(field("owner"), { target: { value: "Анна Петрова" } });
    fireEvent.change(field("students"), { target: { value: "12" } });
    fireEvent.change(field("deadline"), { target: { value: "2026-12-01" } });
    fireEvent.submit(form);

    await waitFor(() => expect(api.count("POST", "/launches")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      university_id: 2,
      program: "Разработка на Python",
      product: "Python",
      owner: "Анна Петрова",
      students: 12,
      deadline: "2026-12-01",
    });
    const students = await within(dialog).findByText("Слишком много обучающихся");
    expect(students.closest("label")?.querySelector("input")?.name).toBe("students");
    const university = within(dialog).getByText("Учебное заведение не найдено");
    expect(university.closest("label")?.querySelector("select")?.name).toBe(
      "university_id",
    );
    expect(within(dialog).getByRole("alert").textContent).toBe(
      "Проверьте заполненные поля (код VALIDATION_ERROR)",
    );
  });
});
