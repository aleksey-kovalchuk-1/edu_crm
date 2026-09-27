import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

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

    expect(await screen.findByText(/главному администратору/)).toBeTruthy();
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
