import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

const ADMIN_SESSION = () => sessionFixture(["crm-superadmin", "crm-admin"]);

describe("settings users page", () => {
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
      "GET /admin/users": () => ({ total: 1, users: [] }),
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
      "GET /admin/users": () => ({ total: 0, users: [] }),
    });
    renderApp("/settings/users");
    await screen.findByText(/Keycloak Admin API не настроен/);
  });

  it("also shows the full user directory below the pending list", async () => {
    mockApi({
      "GET /auth/me": ADMIN_SESSION,
      "GET /admin/pending-registrations": () => ({ available: true, pending: [] }),
      "GET /admin/users": () => ({
        total: 1,
        users: [{ id: 1, email: "anna@demo.local", full_name: "Анна Демо", roles: ["crm-user"], is_active: true, created_at: "2026-01-01T00:00:00Z", last_login_at: null }],
      }),
    });
    renderApp("/settings/users");
    await screen.findByText("anna@demo.local");
  });
});
