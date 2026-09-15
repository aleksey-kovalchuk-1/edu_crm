import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { loginUrl, registerUrl, safeNextPath } from "../api/auth";
import { browser } from "../lib/browser";
import {
  CSRF_TOKEN,
  apiError,
  deferred,
  mockApi,
  renderApp,
  sessionFixture,
} from "../test/utils";

const unauthenticated = () =>
  apiError(401, "UNAUTHENTICATED", "Требуется вход в систему");
const assign = () => vi.mocked(browser.assign);
const location = () => screen.getByTestId("location").textContent;
const pause = (ms = 50) => new Promise((r) => setTimeout(r, ms));

describe("auth gate", () => {
  it("redirects to login with the current path on a first visit without a session", async () => {
    const api = mockApi({ "GET /auth/me": unauthenticated });
    renderApp("/interactions?view=board");
    await waitFor(() => expect(assign()).toHaveBeenCalledTimes(1));
    expect(assign()).toHaveBeenCalledWith(
      "/api/v1/auth/login?next=%2Finteractions%3Fview%3Dboard",
    );
    expect(api.count("GET", "/launches")).toBe(0);
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("normalises the next path", () => {
    expect(safeNextPath("/tasks?x=1")).toBe("/tasks?x=1");
    expect(safeNextPath("//evil.example/x")).toBe("/");
    expect(safeNextPath("/a\\b")).toBe("/");
    expect(safeNextPath("tasks")).toBe("/");
    expect(loginUrl("//evil.example")).toBe("/api/v1/auth/login?next=%2F");
    expect(registerUrl("//evil.example")).toBe("/api/v1/auth/register?next=%2F");
    expect(registerUrl("/tasks?view=1")).toBe(
      "/api/v1/auth/register?next=%2Ftasks%3Fview%3D1",
    );
  });

  it.each([
    ["LOGIN_CANCELLED", "Вход отменён."],
    ["LOGIN_EXPIRED", "Время на вход истекло. Попробуйте ещё раз."],
    [
      "LOGIN_FAILED",
      "Не удалось выполнить вход. Попробуйте ещё раз или обратитесь к администратору.",
    ],
    [
      "NO_ACCESS",
      "У вашей учётной записи нет доступа к CRM. Обратитесь к администратору.",
    ],
  ])("explains auth_error=%s and waits for the user", async (code, message) => {
    const api = mockApi({ "GET /auth/me": unauthenticated });
    renderApp(`/?auth_error=${code}`);
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    const button = screen.getByRole("button", { name: /Войти через Keycloak/ });
    expect(document.activeElement).toBe(button);
    expect(api.count("GET", "/auth/me")).toBe(1);
    expect(assign()).not.toHaveBeenCalled();

    fireEvent.click(button);

    expect(assign()).toHaveBeenCalledWith("/api/v1/auth/login?next=%2F");
    await waitFor(() => expect(location()).toBe("/"));
    expect(assign()).toHaveBeenCalledTimes(1);
  });

  it("stops the login loop and keeps the query string for the retry", async () => {
    sessionStorage.setItem("edu-crm:login-redirect-at", String(Date.now()));
    mockApi({ "GET /auth/me": unauthenticated });
    renderApp("/tasks?view=1");
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось завершить вход. Проверьте, что браузер разрешает cookie для этого сайта, и попробуйте снова.",
    );
    expect(location()).toBe("/tasks?view=1&auth_error=SESSION_NOT_SAVED");
    expect(assign()).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Войти через Keycloak/ }));
    expect(assign()).toHaveBeenCalledWith("/api/v1/auth/login?next=%2Ftasks%3Fview%3D1");
  });

  it("offers registration next to sign-in on the login screen", async () => {
    mockApi({ "GET /auth/me": unauthenticated });
    renderApp("/tasks?auth_error=LOGIN_FAILED");
    await screen.findByRole("alert");
    const button = screen.getByRole("button", { name: "Зарегистрироваться" });
    expect(assign()).not.toHaveBeenCalled();

    fireEvent.click(button);

    expect(assign()).toHaveBeenCalledWith(
      "/api/v1/auth/register?next=%2Ftasks",
    );
    await waitFor(() => expect(location()).toBe("/tasks"));
    expect(assign()).toHaveBeenCalledTimes(1);
  });

  it("offers registration on the logged-out screen", async () => {
    mockApi({ "GET /auth/me": unauthenticated });
    renderApp("/?logged_out=1");
    const button = await screen.findByRole("button", {
      name: "Зарегистрироваться",
    });
    expect(assign()).not.toHaveBeenCalled();

    fireEvent.click(button);

    expect(assign()).toHaveBeenCalledWith("/api/v1/auth/register?next=%2F");
  });

  it("does not offer registration once signed in", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture() });
    renderApp("/");
    await screen.findByText("Анна Петрова");
    expect(
      screen.queryByRole("button", { name: "Зарегистрироваться" }),
    ).toBeNull();
  });

  it("shows a no-access screen for a session without CRM roles", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["offline_access"]) });
    renderApp("/");
    expect((await screen.findByRole("alert")).textContent).toContain(
      "нет доступа к CRM",
    );
    expect(screen.getByRole("button", { name: /Выйти/ })).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Зарегистрироваться" }),
    ).toBeNull();
    expect(assign()).not.toHaveBeenCalled();
  });
});

describe("session ending mid-use", () => {
  it("keeps the page and form input, and logs in only when asked", async () => {
    const api = mockApi({
      "GET /auth/me": () =>
        api.count("GET", "/auth/me") > 1 ? unauthenticated() : sessionFixture(),
      "POST /universities": unauthenticated,
    });
    renderApp("/universities");
    fireEvent.click(await screen.findByRole("button", { name: /Добавить заведение/ }));
    const form = (
      await screen.findByRole("dialog", { name: "Новое учебное заведение" })
    ).querySelector("form")!;
    fireEvent.change(form.querySelector('[name="name"]')!, {
      target: { value: "Колледж" },
    });
    fireEvent.submit(form);

    const expired = await screen.findByRole("dialog", { name: "Сессия истекла" });
    const button = within(expired).getByRole("button", { name: "Войти снова" });
    expect(document.activeElement).toBe(button);
    expect(form.isConnected).toBe(true);
    expect((form.querySelector('[name="name"]') as HTMLInputElement).value).toBe(
      "Колледж",
    );
    expect(screen.getByText("Колледж связи")).toBeTruthy();
    await pause();
    expect(assign()).not.toHaveBeenCalled();

    fireEvent.click(button);
    expect(assign()).toHaveBeenCalledWith("/api/v1/auth/login?next=%2Funiversities");
  });

  it("rolls back an optimistic toggle when the session has ended", async () => {
    const patch = deferred<unknown>();
    const api = mockApi({
      "GET /auth/me": () =>
        api.count("GET", "/auth/me") > 1 ? unauthenticated() : sessionFixture(),
      "PATCH /tasks/1": () => patch.promise,
    });
    renderApp("/tasks");
    const checkbox = (await screen.findByRole("checkbox", {
      name: "Согласовать договор",
    })) as HTMLInputElement;
    fireEvent.click(checkbox);
    await waitFor(() => expect(api.count("PATCH", "/tasks/1")).toBe(1));
    expect(checkbox.checked).toBe(true);
    patch.resolve(unauthenticated());
    expect(await screen.findByRole("dialog", { name: "Сессия истекла" })).toBeTruthy();
    await waitFor(() => expect(checkbox.checked).toBe(false));
    expect(checkbox.isConnected).toBe(true);
    expect(assign()).not.toHaveBeenCalled();
  });

  it("does not loop when a data endpoint returns 401 but the session is valid", async () => {
    const api = mockApi({ "GET /tasks": unauthenticated });
    renderApp("/tasks");
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Требуется вход в систему (код UNAUTHENTICATED)",
    );
    await waitFor(() => expect(api.count("GET", "/auth/me")).toBe(2));
    await pause(100);
    expect(api.count("GET", "/auth/me")).toBe(2);
    expect(api.count("GET", "/tasks")).toBe(1);
    expect(screen.queryByRole("dialog", { name: "Сессия истекла" })).toBeNull();
    expect(assign()).not.toHaveBeenCalled();
  });
});

describe("csrf and permissions", () => {
  const csrfInvalid = () =>
    apiError(403, "CSRF_INVALID", "Страница устарела: обновите её и повторите действие");

  it("re-reads the session and retries once on CSRF_INVALID", async () => {
    const api = mockApi({
      "GET /auth/me": () =>
        sessionFixture(
          ["crm-supervisor"],
          api.count("GET", "/auth/me") > 1 ? "csrf-new" : CSRF_TOKEN,
        ),
      "PATCH /tasks/1": (call) => {
        if (call.headers["x-csrf-token"] !== "csrf-new") return csrfInvalid();
        api.data.tasks = api.data.tasks.map((t) => (t.id === 1 ? { ...t, done: true } : t));
        return api.data.tasks[0];
      },
    });
    renderApp("/tasks");
    const checkbox = (await screen.findByRole("checkbox", {
      name: "Согласовать договор",
    })) as HTMLInputElement;
    fireEvent.click(checkbox);
    await waitFor(() => expect(api.count("PATCH", "/tasks/1")).toBe(2));
    await waitFor(() => expect(checkbox.disabled).toBe(false));
    expect(api.count("GET", "/auth/me")).toBe(2);
    expect(checkbox.checked).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the message when the retry is refused again", async () => {
    const api = mockApi({ "PATCH /tasks/1": csrfInvalid });
    renderApp("/tasks");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Согласовать договор" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Страница устарела: обновите её и повторите действие (код CSRF_INVALID)",
    );
    expect(api.count("PATCH", "/tasks/1")).toBe(2);
    expect(api.count("GET", "/auth/me")).toBe(2);
  });

  it("sends the CSRF token when creating and not on reads", async () => {
    const api = mockApi({
      "POST /universities": (call) => [201, { id: 3, ...(call.body as object) }],
    });
    renderApp("/universities");
    fireEvent.click(await screen.findByRole("button", { name: /Добавить заведение/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новое учебное заведение" });
    const form = dialog.querySelector("form")!;
    fireEvent.change(form.querySelector('[name="name"]')!, { target: { value: "Колледж" } });
    fireEvent.change(form.querySelector('[name="city"]')!, { target: { value: "Томск" } });
    fireEvent.submit(form);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.calls.find((c) => c.method === "POST")?.headers["x-csrf-token"]).toBe(
      CSRF_TOKEN,
    );
    const reads = api.calls.filter((c) => c.method === "GET");
    expect(reads.length).toBeGreaterThan(0);
    expect(reads.some((c) => "x-csrf-token" in c.headers)).toBe(false);
  });

  it("shows the server message and code on 403 FORBIDDEN", async () => {
    mockApi({
      "POST /universities": () =>
        apiError(403, "FORBIDDEN", "Недостаточно прав для этого действия"),
    });
    renderApp("/universities");
    fireEvent.click(await screen.findByRole("button", { name: /Добавить заведение/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новое учебное заведение" });
    fireEvent.submit(dialog.querySelector("form")!);
    expect((await within(dialog).findByRole("alert")).textContent).toBe(
      "Недостаточно прав для этого действия (код FORBIDDEN)",
    );
  });

  it.each([
    [["crm-user"], "Менеджер", false],
    [["crm-supervisor"], "Руководитель", true],
    [["crm-user", "crm-admin"], "Администратор", true],
  ])("roles %j: label %s, can add universities: %s", async (roles, label, canCreate) => {
    mockApi({ "GET /auth/me": () => sessionFixture(roles) });
    renderApp("/universities");
    expect(await screen.findByText(label)).toBeTruthy();
    expect(screen.getByText("Анна Петрова")).toBeTruthy();
    expect(screen.getAllByText("АП")).toHaveLength(2);
    // Read-only data stays visible for every role.
    expect(await screen.findByText("Колледж связи")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Добавить заведение/ }) !== null).toBe(
      canCreate,
    );
  });
});

describe("logout", () => {
  const keycloakLogout =
    "http://localhost:8080/auth/realms/edu-crm/protocol/openid-connect/logout?client_id=edu-crm-api";

  function mockLogout(respond: () => unknown) {
    let done = false;
    const api = mockApi({
      "GET /auth/me": () => (done ? unauthenticated() : sessionFixture()),
      "POST /auth/logout": () => {
        done = true;
        return respond();
      },
    });
    return api;
  }

  async function expectLoggedOutScreen() {
    expect(
      await screen.findByRole("heading", { level: 1, name: "Вы вышли из системы" }),
    ).toBeTruthy();
    const button = screen.getByRole("button", { name: /Войти снова/ });
    await waitFor(() => expect(document.activeElement).toBe(button));
    await pause();
    expect(assign()).not.toHaveBeenCalled();
    return button;
  }

  it("shows the logged-out screen when the backend confirmed logout", async () => {
    const api = mockLogout(() => ({ logout_url: "http://localhost:8080/" }));
    renderApp("/analytics");
    fireEvent.click(await screen.findByRole("button", { name: "Выйти" }));
    const button = await expectLoggedOutScreen();
    expect(location()).toBe("/?logged_out=1");
    expect(api.calls.find((c) => c.path === "/auth/logout")).toMatchObject({
      method: "POST",
      headers: { "x-csrf-token": CSRF_TOKEN },
    });
    await waitFor(() => expect(api.count("GET", "/auth/me")).toBe(2));
    fireEvent.click(button);
    expect(assign()).toHaveBeenCalledWith("/api/v1/auth/login?next=%2F");
  });

  it("goes to Keycloak when the backend could not end the SSO session", async () => {
    mockLogout(() => ({ logout_url: keycloakLogout }));
    renderApp("/analytics");
    fireEvent.click(await screen.findByRole("button", { name: "Выйти" }));
    await waitFor(() => expect(assign()).toHaveBeenCalledWith(keycloakLogout));
    expect(assign()).toHaveBeenCalledTimes(1);
  });

  it("treats 401 from logout as already logged out", async () => {
    mockLogout(unauthenticated);
    renderApp("/analytics");
    fireEvent.click(await screen.findByRole("button", { name: "Выйти" }));
    await expectLoggedOutScreen();
    expect(screen.queryByRole("dialog", { name: "Сессия истекла" })).toBeNull();
  });

  it("does not auto-redirect on a fresh visit to the logged-out page", async () => {
    const api = mockApi({ "GET /auth/me": unauthenticated });
    renderApp("/?logged_out=1");
    await expectLoggedOutScreen();
    expect(api.count("GET", "/auth/me")).toBe(1);
  });

  it("shows an error when logout fails", async () => {
    mockApi({
      "POST /auth/logout": () => apiError(500, "INTERNAL_ERROR", "Внутренняя ошибка сервера"),
    });
    renderApp("/analytics");
    const button = await screen.findByRole("button", { name: "Выйти" });
    fireEvent.click(button);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Внутренняя ошибка сервера (код INTERNAL_ERROR)",
    );
    expect(assign()).not.toHaveBeenCalled();
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });
});
