import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

describe("settings backups", () => {
  it("shows only sanitized encrypted backup pairs to a superadmin", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-superadmin", "crm-admin"]),
      "GET /admin/backups": () => ({ available: true, reason: null, generated_at: "2026-09-27T12:00:00Z", backups: [
        { created_at: "2026-09-27T12:00:00Z", source: "daily-20260927", database_bytes: 1048576, attachments_bytes: 2097152, verified: true },
        { created_at: "2026-09-26T12:00:00Z", source: "release-1", database_bytes: 1024, attachments_bytes: 2048, verified: false },
      ] }),
    });
    renderApp("/settings/backups");
    await screen.findByText("Ежедневная копия");
    screen.getByText("Перед публикацией");
    screen.getByText("Проверена");
    screen.getByText("Сохранена, без проверки");
    expect(api.callsTo("GET", "/admin/backups")).toHaveLength(1);
  });

  it("explains when the server has not published backup status", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-superadmin", "crm-admin"]),
      "GET /admin/backups": () => ({ available: false, reason: "missing", generated_at: null, backups: [] }),
    });
    renderApp("/settings/backups");
    await screen.findByText(/Сведения о резервных копиях пока не поступили/);
  });

  it("does not request backup metadata for a manager", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/backups");
    await screen.findByText(/Нет доступа|Доступ запрещён|Страница недоступна/);
    expect(api.callsTo("GET", "/admin/backups")).toHaveLength(0);
  });
});
