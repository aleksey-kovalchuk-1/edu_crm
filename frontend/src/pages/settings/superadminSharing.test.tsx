import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

const SUPER = () => sessionFixture(["crm-superadmin", "crm-admin", "crm-supervisor"]);
const person = (id: string, username: string, roles: string[], extra: object = {}) => ({
  keycloak_id: id, username, email: `${username}@mail.ru`, full_name: username, roles, is_active: true,
  last_login_at: null, setup_pending: false, primary_superadmin: false, ...extra,
});
const directory = (canRevoke: boolean) => () => ({
  available: true, total: 4, can_revoke_superadmin: canRevoke,
  users: [
    person("kc-irina", "irina_super_admin", ["crm-superadmin"], { primary_superadmin: true }),
    person("kc-olga", "olga", ["crm-admin"]),
    person("kc-petr", "petr", ["crm-superadmin"]),
    person("kc-anna", "anna", ["crm-user"]),
  ],
});
const base = (canRevoke: boolean) => ({
  "GET /auth/me": SUPER,
  "GET /admin/pending-registrations": () => ({ available: true, pending: [] }),
  "GET /admin/users": directory(canRevoke),
});
const rowOf = async (username: string) => {
  const table = await within(await screen.findByRole("region", { name: "Пользователи CRM" })).findByRole("table");
  return within(table).getAllByText(username)[0].closest("tr") as HTMLElement;
};

describe("superadmin rights and the head role", () => {
  it("offers «Руководитель» in the role picker", async () => {
    mockApi(base(true));
    renderApp("/settings/users");
    fireEvent.click(await screen.findByRole("button", { name: "Изменить роль пользователя anna" }));
    const options = [...within(screen.getByRole("form", { name: "Роль пользователя anna" })).getByLabelText("Новая роль").querySelectorAll("option")];
    expect(options.map((o) => o.textContent)).toEqual(["КАМ", "Руководитель", "Администратор"]);
  });

  it("lets a superadmin make an administrator a superadmin, after confirming", async () => {
    const api = mockApi({ ...base(false), "POST /admin/users/kc-olga/superadmin": () => ({ keycloak_id: "kc-olga", username: "olga", role: "crm-superadmin", password_setup: "not_needed" }) });
    renderApp("/settings/users");
    const olga = await rowOf("olga");
    expect(within(await rowOf("anna")).queryByRole("button", { name: /Сделать суперадминистратором/ })).toBeNull();
    fireEvent.click(within(olga).getByRole("button", { name: "Сделать суперадминистратором: olga" }));
    const dialog = await screen.findByRole("dialog", { name: "Передать права суперадминистратора?" });
    expect(dialog.textContent).toContain("Снять их сможет только главный суперадминистратор");
    fireEvent.click(within(dialog).getByRole("button", { name: "Передать права" }));
    await waitFor(() => expect(api.callsTo("POST", "/admin/users/kc-olga/superadmin")).toHaveLength(1));
    expect(await screen.findByText(/olga теперь суперадминистратор/)).toBeTruthy();
  });

  it("shows «Снять права суперадминистратора» only to the primary superadmin, and never on her own row", async () => {
    const api = mockApi({ ...base(true), "DELETE /admin/users/kc-petr/superadmin": () => [204, undefined] });
    renderApp("/settings/users");
    const irina = await rowOf("irina_super_admin");
    expect(within(irina).getByText("Главный суперадминистратор")).toBeTruthy();
    expect(within(irina).queryByRole("button")).toBeNull();
    fireEvent.click(within(await rowOf("petr")).getByRole("button", { name: "Снять права суперадминистратора: petr" }));
    const dialog = await screen.findByRole("dialog", { name: "Снять права суперадминистратора?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Снять права" }));
    await waitFor(() => expect(api.callsTo("DELETE", "/admin/users/kc-petr/superadmin")).toHaveLength(1));
    expect(await screen.findByText(/petr снова администратор/)).toBeTruthy();
  });

  it("gives other superadmins no way to revoke", async () => {
    mockApi(base(false));
    renderApp("/settings/users");
    const petr = await rowOf("petr");
    expect(within(petr).queryByRole("button", { name: /Снять права/ })).toBeNull();
    expect(within(petr).getByText(/Снять права может главный суперадминистратор/)).toBeTruthy();
  });
});
