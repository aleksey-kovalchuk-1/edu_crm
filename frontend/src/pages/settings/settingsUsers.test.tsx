import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

const ADMIN_SESSION = () => sessionFixture(["crm-superadmin", "crm-admin"]);

describe("settings users page", () => {
  it("lets Irina create an administrator and shows the initial password once", async () => {
    const api = mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({ available: true, pending: [] }),
      "GET /admin/users": () => ({ available: true, total: 0, users: [] }),
      "POST /admin/users": () => [201, {
        keycloak_id: "kc-new", username: "admin_1", email: "admin_1@educrm-demo.ru",
        role: "crm-admin", temporary_password: "TemporarySecret123456789",
      }],
    });
    renderApp("/settings/users");
    const form = await screen.findByRole("form", { name: "Новая учётная запись" });
    fireEvent.change(within(form).getByLabelText("Логин"), { target: { value: "admin_1" } });
    fireEvent.change(within(form).getByLabelText("Электронная почта"), { target: { value: "admin_1@educrm-demo.ru" } });
    fireEvent.change(within(form).getByLabelText("Имя"), { target: { value: "Администратор" } });
    fireEvent.change(within(form).getByLabelText("Фамилия"), { target: { value: "Один" } });
    fireEvent.change(within(form).getByLabelText("Роль"), { target: { value: "crm-admin" } });
    fireEvent.submit(form);
    await waitFor(() => expect(api.callsTo("POST", "/admin/users")).toHaveLength(1));
    expect(api.callsTo("POST", "/admin/users")[0].body).toMatchObject({
      username: "admin_1", email: "admin_1@educrm-demo.ru", role: "crm-admin",
    });
    expect(await screen.findByText("TemporarySecret123456789")).toBeTruthy();
    expect(within(form).getByLabelText("Роль").querySelectorAll("option")).toHaveLength(2);
  });

  it("shows pending registrations and approves one", async () => {
    let approved: string[] = [];
    const api = mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({
        available: true,
        pending: approved.includes("kc-1")
          ? []
          : [{ keycloak_id: "kc-1", email: "newbie@demo.local", username: "newbie" }],
      }),
      "POST /admin/pending-registrations/kc-1/approve": () => {
        approved = [...approved, "kc-1"];
        return [204, undefined];
      },
      "GET /admin/users": () => ({ available: true, total: 1, users: [] }),
    });
    renderApp("/settings/users");
    await screen.findByText("newbie@demo.local");

    fireEvent.click(screen.getByRole("button", { name: "Одобрить" }));

    await waitFor(() => expect(api.callsTo("POST", "/admin/pending-registrations/kc-1/approve")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText("newbie@demo.local")).toBeNull());
    screen.getByText("Заявок на доступ нет.");
  });

  it("shows an unavailable notice when the Keycloak Admin API isn't configured", async () => {
    mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({ available: false, pending: [] }),
      "GET /admin/users": () => ({ available: false, total: 0, users: [] }),
    });
    renderApp("/settings/users");
    await screen.findByText(/Keycloak Admin API не настроен/);
  });

  it("also shows the full user directory below the pending list", async () => {
    mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({ available: true, pending: [] }),
      "GET /admin/users": () => ({
        available: true, total: 1,
        users: [{ keycloak_id: "kc-1", username: "anna", email: "anna@demo.local", full_name: "Анна Демо", roles: ["crm-user"], is_active: true, last_login_at: null }],
      }),
    });
    renderApp("/settings/users");
    await screen.findByText("anna@demo.local");
  });
});
