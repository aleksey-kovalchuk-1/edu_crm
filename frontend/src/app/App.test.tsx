import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CSRF_TOKEN, apiError, mockApi, renderApp } from "../test/utils";

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

describe("task creation", () => {
  it("creates a task and opens its detail page", async () => {
    const api = mockApi({
      "POST /tasks": (call) => {
        const body = call.body as { title: string };
        return [201, { ...api.data.task, id: 2, title: body.title }];
      },
      "GET /tasks/2": () => ({ ...api.data.task, id: 2, title: "Новая задача" }),
    });
    renderApp("/tasks");
    fireEvent.click(await screen.findByRole("button", { name: /Создать задачу/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новая задача" });
    fireEvent.change(
      within(dialog).getByPlaceholderText("Например, собрать документы"),
      { target: { value: "Новая задача" } },
    );
    fireEvent.submit(dialog.querySelector("form")!);

    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")).toMatchObject({
      method: "POST",
      path: "/tasks",
      headers: { "x-csrf-token": CSRF_TOKEN },
    });
    expect(
      await screen.findByRole("heading", { level: 2, name: "Новая задача" }),
    ).toBeTruthy();
  });

  it("shows the server's field error and keeps the form open", async () => {
    mockApi({
      "POST /tasks": () =>
        apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
          { field: "title", message: "Название обязательно", type: "missing" },
        ]),
    });
    renderApp("/tasks");
    fireEvent.click(await screen.findByRole("button", { name: /Создать задачу/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новая задача" });
    fireEvent.change(
      within(dialog).getByPlaceholderText("Например, собрать документы"),
      { target: { value: "x" } },
    );
    fireEvent.submit(dialog.querySelector("form")!);
    expect(await within(dialog).findByText("Название обязательно")).toBeTruthy();
    expect(within(dialog).getByRole("alert").textContent).toBe(
      "Проверьте заполненные поля (код VALIDATION_ERROR)",
    );
  });
});

describe("interaction detail navigation", () => {
  it("opens the interaction detail page from the board card", async () => {
    mockApi();
    renderApp("/interactions");
    await screen.findByText("ВЗ-0001");
    expect(columnOf("ВЗ-0001")).toBe("Документы");
    fireEvent.click(screen.getByRole("link", { name: /Аналитика данных/ }));
    expect(
      await screen.findByRole("heading", { level: 2, name: "Аналитика данных" }),
    ).toBeTruthy();
    expect((await screen.findByTestId("location")).textContent).toBe("/interactions/1");
  });

  it("opens the interaction detail page from the overview table", async () => {
    mockApi();
    renderApp("/");
    fireEvent.click(await screen.findByRole("link", { name: "Аналитика данных" }));
    expect(
      await screen.findByRole("heading", { level: 2, name: "Аналитика данных" }),
    ).toBeTruthy();
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
    renderApp("/interactions");
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
