import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

describe("settings account page", () => {
  it("shows the signed-in user and logs out on click", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"]),
      "POST /auth/logout": () => ({ logout_url: "http://localhost:8080/" }),
    });
    renderApp("/settings/account");
    await screen.findByText(/anna\.petrova@example\.test/);
    fireEvent.click(screen.getByRole("button", { name: "Выйти из аккаунта" }));
    await waitFor(() => expect(api.callsTo("POST", "/auth/logout")).toHaveLength(1));
  });

  it("hides the user directory from a regular user", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/account");
    await screen.findByText(/anna\.petrova@example\.test/);
    expect(screen.queryByText("Пользователи CRM")).toBeNull();
  });

  it("shows the user directory with total count to a superadmin", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-superadmin", "crm-admin"]),
      "GET /admin/users": () => ({
        total: 2,
        users: [
          { id: 1, email: "anna@demo.local", full_name: "Анна Демо", roles: ["crm-user"], is_active: true, created_at: "2026-01-01T00:00:00Z", last_login_at: null },
          { id: 2, email: "oleg@demo.local", full_name: "Олег Кузнецов", roles: ["crm-admin"], is_active: true, created_at: "2026-01-01T00:00:00Z", last_login_at: null },
        ],
      }),
    });
    renderApp("/settings/account");
    await screen.findByText("Всего: 2");
    screen.getByText("anna@demo.local");
    screen.getByText("oleg@demo.local");
  });
});
