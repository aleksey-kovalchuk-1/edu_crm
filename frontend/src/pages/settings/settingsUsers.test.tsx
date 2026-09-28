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

  it("shows pending registrations and grants manager access", async () => {
    let approved: string[] = [];
    const api = mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({
        available: true,
        pending: approved.includes("kc-1")
          ? []
          : [{ keycloak_id: "kc-1", email: "newbie@demo.local", username: "newbie" }],
      }),
      "PATCH /admin/users/kc-1/role": () => {
        approved = [...approved, "kc-1"];
        return [204, undefined];
      },
      "GET /admin/users": () => ({ available: true, total: 1, users: [] }),
    });
    renderApp("/settings/users");
    await screen.findByText("newbie@demo.local");

    fireEvent.click(screen.getByRole("button", { name: "Выдать доступ" }));

    await waitFor(() => expect(api.callsTo("PATCH", "/admin/users/kc-1/role")).toHaveLength(1));
    expect(api.callsTo("PATCH", "/admin/users/kc-1/role")[0].body).toEqual({ role: "crm-user" });
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

  it("lets Irina change an existing manager to an administrator", async () => {
    const api = mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({ available: true, pending: [] }),
      "GET /admin/users": () => ({
        available: true, total: 2,
        users: [
          { keycloak_id: "kc-manager", username: "manager_1", email: "manager@example.test", full_name: "Менеджер", roles: ["crm-user"], is_active: true, last_login_at: null },
          { keycloak_id: "kc-irina", username: "irina_super_admin", email: "irina@example.test", full_name: "Ирина", roles: ["crm-superadmin", "crm-admin", "crm-supervisor"], is_active: true, last_login_at: null },
        ],
      }),
      "PATCH /admin/users/kc-manager/role": () => [200, { keycloak_id: "kc-manager", username: "manager_1", role: "crm-admin" }],
    });
    renderApp("/settings/users");
    const editor = await screen.findByRole("form", { name: "Роль пользователя manager_1" });
    fireEvent.change(within(editor).getByLabelText("Новая роль"), { target: { value: "crm-admin" } });
    fireEvent.submit(editor);

    await waitFor(() => expect(api.callsTo("PATCH", "/admin/users/kc-manager/role")).toHaveLength(1));
    expect(api.callsTo("PATCH", "/admin/users/kc-manager/role")[0].body).toEqual({ role: "crm-admin" });
    expect(screen.queryByRole("form", { name: "Роль пользователя irina_super_admin" })).toBeNull();
  });

  it("lets Irina assign the administrator role to a pending Keycloak account", async () => {
    const api = mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({
        available: true, pending: [{ keycloak_id: "kc-new", username: "new_admin", email: "new@example.test" }],
      }),
      "GET /admin/users": () => ({ available: true, total: 0, users: [] }),
      "PATCH /admin/users/kc-new/role": () => [200, { keycloak_id: "kc-new", username: "new_admin", role: "crm-admin" }],
    });
    renderApp("/settings/users");
    const editor = await screen.findByRole("form", { name: "Доступ пользователя new_admin" });
    fireEvent.change(within(editor).getByLabelText("Роль"), { target: { value: "crm-admin" } });
    fireEvent.submit(editor);

    await waitFor(() => expect(api.callsTo("PATCH", "/admin/users/kc-new/role")).toHaveLength(1));
    expect(api.callsTo("PATCH", "/admin/users/kc-new/role")[0].body).toEqual({ role: "crm-admin" });
  });

  describe("users table", () => {
    const LONG = "konstantin.dlinnofamilnyy-verkhnepyshminskiy@verkhnepyshminskiy-politekhnicheskiy-universitet.example.ru";
    const users = () => ({
      available: true, total: 3,
      users: [
        { keycloak_id: "kc-irina", username: "irina_super_admin", email: "irina@example.test", full_name: "Ирина Руководитель", roles: ["crm-superadmin", "crm-admin", "crm-supervisor"], is_active: true, last_login_at: null },
        { keycloak_id: "kc-long", username: "konstantin.dlinnofamilnyy-verkhnepyshminskiy", email: LONG, full_name: "Константин Длиннофамильный", roles: ["crm-user"], is_active: true, last_login_at: null },
        { keycloak_id: "kc-admin", username: "admin_1", email: "admin_1@example.test", full_name: "Администратор 1", roles: ["crm-user", "crm-admin"], is_active: true, last_login_at: null },
      ],
    });

    it("shows one short role label per user, and only «Суперадминистратор» for Irina", async () => {
      mockApi({ "GET /auth/me": ADMIN_SESSION, "GET /admin/pending-registrations": () => ({ available: true, pending: [] }), "GET /admin/users": users });
      renderApp("/settings/users");
      const table = await within(await screen.findByRole("region", { name: "Пользователи CRM" })).findByRole("table");
      const roleOf = (login: string) => {
        const row = within(table).getByText(login).closest("tr") as HTMLElement;
        return (row.querySelector('td[data-label="Роль"]') as HTMLElement).textContent;
      };
      expect(roleOf("irina_super_admin")).toBe("Суперадминистратор");
      expect(roleOf("konstantin.dlinnofamilnyy-verkhnepyshminskiy")).toBe("КАМ");
      expect(roleOf("admin_1")).toBe("Администратор");
      expect(table.textContent).not.toMatch(/,\s*(Руководитель|Администратор)/);
    });

    it("keeps Irina's role protected and every other user's role editor labelled", async () => {
      mockApi({ "GET /auth/me": ADMIN_SESSION, "GET /admin/pending-registrations": () => ({ available: true, pending: [] }), "GET /admin/users": users });
      renderApp("/settings/users");
      const table = await within(await screen.findByRole("region", { name: "Пользователи CRM" })).findByRole("table");
      const irina = within(table).getByText("irina_super_admin").closest("tr") as HTMLElement;
      expect(within(irina).getByText("Защищённая роль")).toBeTruthy();
      const editor = screen.getByRole("form", { name: "Роль пользователя konstantin.dlinnofamilnyy-verkhnepyshminskiy" });
      expect(within(editor).getByLabelText("Новая роль")).toBeTruthy();
      expect(within(editor).getByRole("button", { name: "Сохранить роль" })).toBeTruthy();
    });

    it("stacks into labelled rows on phones and lets long logins and emails wrap", async () => {
      mockApi({ "GET /auth/me": ADMIN_SESSION, "GET /admin/pending-registrations": () => ({ available: true, pending: [] }), "GET /admin/users": users });
      renderApp("/settings/users");
      const table = await within(await screen.findByRole("region", { name: "Пользователи CRM" })).findByRole("table");
      expect(table.className).toContain("stack-table");
      expect(table.className).toContain("users-table");
      const row = within(table).getByText(LONG).closest("tr") as HTMLElement;
      expect([...row.querySelectorAll("td")].map((c) => c.getAttribute("data-label"))).toEqual(["Пользователь", "Роль", "Статус", "Последний вход", "Изменить роль"]);
      expect(within(row).getByText(LONG).className).toContain("wrap-anywhere");
    });

    it("frames every section of the page like the other Settings pages", async () => {
      mockApi({ "GET /auth/me": ADMIN_SESSION, "GET /admin/pending-registrations": () => ({ available: true, pending: [] }), "GET /admin/users": users });
      renderApp("/settings/users");
      for (const name of ["Новая учётная запись", "Заявки на доступ", "Пользователи CRM"]) {
        const section = await screen.findByRole("region", { name });
        expect(section.className).toContain("settings-panel");
        expect(section.querySelector(".settings-body")).toBeTruthy();
      }
    });
  });
});

