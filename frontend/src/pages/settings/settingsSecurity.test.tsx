import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

const sessions = [
  { id: "aaaa1111bbbb2222", device: "Chrome · Windows", ip: "10.0.0.1", created_at: "2026-09-27T08:00:00Z", last_active_at: "2026-09-27T10:00:00Z", current: true },
  { id: "cccc3333dddd4444", device: "Safari · iOS", ip: "10.0.0.2", created_at: "2026-09-26T08:00:00Z", last_active_at: "2026-09-26T09:00:00Z", current: false },
];

describe("settings security", () => {
  it("lists sessions, marks this device, and ends another session with the server's message", async () => {
    const api = mockApi({
      "GET /security/sessions": () => sessions,
      "DELETE /security/sessions/cccc3333dddd4444": () => ({ keycloak_ended: false, message: "Сеанс в CRM завершён. Сеанс входа завершится сам после 30 минут бездействия." }),
    });
    renderApp("/settings/security");
    await screen.findByText("Это устройство");
    expect(screen.queryByRole("button", { name: "Завершить сеанс Chrome · Windows" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Завершить сеанс Safari · iOS" }));
    const confirm = await screen.findByRole("dialog", { name: "Завершить сеанс?" });
    expect(confirm.textContent).toMatch(/Safari · iOS/);
    expect(api.callsTo("DELETE", "/security/sessions/cccc3333dddd4444")).toHaveLength(0);
    fireEvent.click(within(confirm).getByRole("button", { name: "Завершить сеанс" }));
    await screen.findByText(/завершится сам после 30 минут/);
    expect(api.callsTo("DELETE", "/security/sessions/cccc3333dddd4444")).toHaveLength(1);
  });

  it("ends all other sessions", async () => {
    const api = mockApi({
      "GET /security/sessions": () => sessions,
      "POST /security/sessions/terminate-others": () => ({ count: 1, keycloak_all_ended: true, message: "Все остальные сеансы завершены." }),
    });
    renderApp("/settings/security");
    fireEvent.click(await screen.findByRole("button", { name: "Завершить все остальные" }));
    const confirm = await screen.findByRole("dialog", { name: "Завершить все остальные сеансы?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Завершить все остальные" }));
    await screen.findByText("Все остальные сеансы завершены.");
    expect(api.callsTo("POST", "/security/sessions/terminate-others")).toHaveLength(1);
  });

  it("does nothing when ending a session is cancelled", async () => {
    const api = mockApi({ "GET /security/sessions": () => sessions });
    renderApp("/settings/security");
    fireEvent.click(await screen.findByRole("button", { name: "Завершить сеанс Safari · iOS" }));
    const confirm = await screen.findByRole("dialog", { name: "Завершить сеанс?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Отмена" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.callsTo("DELETE", "/security/sessions/cccc3333dddd4444")).toHaveLength(0);
  });

  it("announces loading while sessions are fetched", async () => {
    mockApi({ "GET /security/sessions": () => new Promise(() => {}) });
    renderApp("/settings/security");
    expect(await screen.findByText("Загружаем сеансы…")).toBeTruthy();
  });

  it("shows CRM sign-ins and says honestly that the Keycloak journal is not enabled", async () => {
    mockApi({
      "GET /security/login-history": () => ({
        crm: [{ at: "2026-09-27T08:00:00Z", device: "Chrome · Windows", ip: "10.0.0.1", state: "active" }],
        keycloak: { available: false, reason: "disabled", events: [] },
      }),
    });
    renderApp("/settings/security");
    await screen.findByText("Журнал входов недоступен: хранение событий не включено");
    screen.getByText("Активен");
  });

  it("shows Keycloak events when available", async () => {
    mockApi({
      "GET /security/login-history": () => ({
        crm: [],
        keycloak: { available: true, reason: null, events: [
          { at: "2026-09-27T08:00:00Z", type: "LOGIN_ERROR", label: "Неудачная попытка входа", ip: "10.0.0.9", error: "invalid_user_credentials" },
        ] },
      }),
    });
    renderApp("/settings/security");
    await screen.findByText("Неудачная попытка входа");
    screen.getByText("10.0.0.9");
  });

  it("shows the policy with a change-password link, and the admin console link only to admins", async () => {
    mockApi();
    renderApp("/settings/security");
    await screen.findByText("Не короче 12 символов");
    expect(screen.getByRole("link", { name: "Сменить пароль" }).getAttribute("href")).toContain("/account/account-security/signing-in");
    expect(screen.queryByRole("link", { name: "Изменить политику в консоли входа" })).toBeNull();
  });

  it("gives admins the Keycloak console link", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-admin"]),
      "GET /security/password-policy": () => ({
        available: true, rules: ["Не короче 12 символов"], brute_force: "После 30 неудачных попыток вход временно блокируется",
        change_password_url: "http://kc/account/account-security/signing-in",
        admin_console_url: "http://kc/admin/master/console/#/edu-crm/authentication/policies",
      }),
    });
    renderApp("/settings/security");
    await screen.findByText("После 30 неудачных попыток вход временно блокируется");
    await waitFor(() => expect(screen.getByRole("link", { name: "Изменить политику в консоли входа" })).toBeTruthy());
  });

  it("says the policy is unavailable instead of inventing rules", async () => {
    mockApi({
      "GET /security/password-policy": () => ({ available: false, rules: [], brute_force: null, change_password_url: "http://kc/x", admin_console_url: null }),
    });
    renderApp("/settings/security");
    await screen.findByText(/Политика сейчас недоступна/);
  });
});

describe("settings security page", () => {
  it("lets Irina reset a manager password and shows the temporary password once", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-superadmin", "crm-admin"]),
      "GET /admin/users": () => ({
        available: true, total: 1,
        users: [{ keycloak_id: "kc-manager", username: "manager_1", email: "manager@example.test", full_name: "Менеджер", roles: ["crm-user"], is_active: true, last_login_at: null }],
      }),
      "GET /admin/pending-registrations": () => ({ available: true, pending: [] }),
      "POST /admin/users/kc-manager/reset-password": () => [200, {
        keycloak_id: "kc-manager", username: "manager_1", temporary_password: "FreshTemporarySecret123456",
      }],
    });
    renderApp("/settings/security");
    fireEvent.change(await screen.findByLabelText("Учётная запись"), { target: { value: "kc-manager" } });
    fireEvent.click(screen.getByRole("button", { name: "Сбросить пароль" }));

    await waitFor(() => expect(api.callsTo("POST", "/admin/users/kc-manager/reset-password")).toHaveLength(1));
    expect(await screen.findByText("FreshTemporarySecret123456")).toBeTruthy();
  });

  it("does not offer password management to a manager", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/security");

    expect(await screen.findByRole("heading", { name: "Мои сеансы" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Парольная политика" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Сбросить пароль" })).toBeNull();
    expect(api.callsTo("GET", "/admin/users")).toHaveLength(0);
  });

  it("can reset the password of a registered user awaiting a role", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-superadmin", "crm-admin"]),
      "GET /admin/users": () => ({ available: true, total: 0, users: [] }),
      "GET /admin/pending-registrations": () => ({
        available: true,
        pending: [{ keycloak_id: "kc-pending", username: "new_person", email: "new@example.test" }],
      }),
      "POST /admin/users/kc-pending/reset-password": () => [200, {
        keycloak_id: "kc-pending", username: "new_person", temporary_password: "AnotherTemporarySecret123",
      }],
    });
    renderApp("/settings/security");
    fireEvent.change(await screen.findByLabelText("Учётная запись"), { target: { value: "kc-pending" } });
    fireEvent.click(screen.getByRole("button", { name: "Сбросить пароль" }));

    await waitFor(() => expect(api.callsTo("POST", "/admin/users/kc-pending/reset-password")).toHaveLength(1));
    expect(await screen.findByText("AnotherTemporarySecret123")).toBeTruthy();
  });
});
