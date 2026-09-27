import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { backupStatusFixture, mockApi, renderApp, sessionFixture } from "../../test/utils";

// Like Ирина: the superadmin also holds crm-admin (a superadmin-only account has no CRM access in the app shell).
const asSuperadmin = { "GET /auth/me": () => sessionFixture(["crm-admin", "crm-superadmin"]) };

describe("settings backups", () => {
  it("shows the last run, verification, pairs with sizes and retention", async () => {
    mockApi(asSuperadmin);
    renderApp("/settings/backups");
    await screen.findByText(/Успешно/);
    screen.getByText(/Проверена расшифровкой/);
    screen.getByText("2.0 МБ");
    screen.getByText("5.0 МБ");
    screen.getByText(/30 дней/);
  });

  it("warns when the last successful copy is too old", async () => {
    mockApi({ ...asSuperadmin, "GET /backups/status": () => backupStatusFixture({ stale: true }) });
    renderApp("/settings/backups");
    await screen.findByText(/Последняя успешная копия старше 36 часов/);
  });

  it("says honestly when no report exists yet", async () => {
    mockApi({ ...asSuperadmin, "GET /backups/status": () => backupStatusFixture({ available: false, reason: "no_report", last_run: null, pairs: [], retention: null, stale: true }) });
    renderApp("/settings/backups");
    await screen.findByText(/Отчёт о резервном копировании пока не записан/);
  });

  it("requests a manual copy and shows it as requested", async () => {
    let requested = false;
    const api = mockApi({
      ...asSuperadmin,
      "GET /backups/status": () => backupStatusFixture({ pending_request: requested }),
      "POST /backups/manual": () => { requested = true; return [202, { state: "requested" }]; },
    });
    renderApp("/settings/backups");
    fireEvent.click(await screen.findByRole("button", { name: "Создать копию сейчас" }));
    await screen.findByText(/Копия запрошена/);
    expect(api.callsTo("POST", "/backups/manual")).toHaveLength(1);
    expect((screen.getByRole("button", { name: "Создать копию сейчас" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a running copy", async () => {
    mockApi({ ...asSuperadmin, "GET /backups/status": () => backupStatusFixture({
      last_run: { trigger: "manual", label: "manual-20260927-120000", started_at: "2026-09-27T12:00:00Z", finished_at: null, result: "running", verified: null, error: null },
    }) });
    renderApp("/settings/backups");
    expect((await screen.findAllByText(/Выполняется/)).length).toBeGreaterThan(0);
  });

  it("explains a failed run", async () => {
    mockApi({ ...asSuperadmin, "GET /backups/status": () => backupStatusFixture({
      last_run: { trigger: "scheduled", label: "daily-20260927", started_at: "2026-09-27T00:30:00Z", finished_at: "2026-09-27T00:31:00Z", result: "failure", verified: null, error: "attachments_backup_failed" },
    }) });
    renderApp("/settings/backups");
    await screen.findByText(/Ошибка: не удалось создать копию вложений/);
  });

  it("is not available to a regular admin", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-admin"]) });
    renderApp("/settings/backups");
    await waitFor(() => expect(api.callsTo("GET", "/backups/status")).toHaveLength(0));
  });

  it("says the backup service is not responding when a request waits too long", async () => {
    mockApi({ ...asSuperadmin, "GET /backups/status": () => backupStatusFixture({
      pending_request: true, pending_since: new Date(Date.now() - 20 * 60_000).toISOString(),
    }) });
    renderApp("/settings/backups");
    await screen.findByText(/Служба копирования не отвечает/);
    expect(screen.queryByText(/в течение минуты/)).toBeNull();
  });

  it("does not crash on a copy entry without files", async () => {
    mockApi({ ...asSuperadmin, "GET /backups/status": () => backupStatusFixture({
      pairs: [{ label: "daily-20260926", database: null, attachments: null }],
    }) });
    renderApp("/settings/backups");
    await screen.findByText("Ежедневная");
  });
});
