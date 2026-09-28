import { fireEvent, screen } from "@testing-library/react";
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

  it("warns when the newest copy is older than 36 hours", async () => {
    mockApi({
      ...superadmin,
      "GET /admin/backups": () => history(hoursAgo(40)),
    });
    renderApp("/settings/backups");
    await screen.findByText(/Последняя копия старше 36 часов/);
  });

  it("shows a failed latest run with its stage even though the history has no new pair", async () => {
    mockApi({
      ...superadmin,
      "GET /admin/backups": () => history(hoursAgo(1)),
      "GET /admin/backups/run": () => runStatus({ last_run: lastRun("failure", "attachments_backup_failed") }),
    });
    renderApp("/settings/backups");
    await screen.findByText(/Последний запуск завершился ошибкой: не удалось создать копию вложений/);
  });

  it("requests a manual copy and shows it as requested", async () => {
    let requested = false;
    const api = mockApi({
      ...superadmin,
      "GET /admin/backups": () => history(hoursAgo(1)),
      "GET /admin/backups/run": () => runStatus({ pending_request: requested, pending_since: requested ? new Date().toISOString() : null }),
      "POST /admin/backups/manual": () => { requested = true; return [202, { state: "requested" }]; },
    });
    renderApp("/settings/backups");
    fireEvent.click(await screen.findByRole("button", { name: "Создать копию сейчас" }));
    await screen.findByText(/Копия запрошена/);
    expect(api.callsTo("POST", "/admin/backups/manual")).toHaveLength(1);
    expect((screen.getByRole("button", { name: "Создать копию сейчас" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("says the backup service is not responding when a request waits too long", async () => {
    mockApi({
      ...superadmin,
      "GET /admin/backups": () => history(hoursAgo(1)),
      "GET /admin/backups/run": () => runStatus({ pending_request: true, pending_since: new Date(Date.now() - 20 * 60_000).toISOString() }),
    });
    renderApp("/settings/backups");
    await screen.findByText(/Служба копирования не отвечает/);
  });

  it("shows a running copy", async () => {
    mockApi({
      ...superadmin,
      "GET /admin/backups": () => history(hoursAgo(1)),
      "GET /admin/backups/run": () => runStatus({ last_run: lastRun("running") }),
    });
    renderApp("/settings/backups");
    expect((await screen.findAllByText(/Выполняется/)).length).toBeGreaterThan(0);
  });

  it("hides the manual button where manual backups are not set up", async () => {
    mockApi({
      ...superadmin,
      "GET /admin/backups": () => history(hoursAgo(1)),
      "GET /admin/backups/run": () => runStatus({ manual_available: false }),
    });
    renderApp("/settings/backups");
    await screen.findByText("Ежедневная копия");
    expect(screen.queryByRole("button", { name: "Создать копию сейчас" })).toBeNull();
  });
});

const superadmin = { "GET /auth/me": () => sessionFixture(["crm-superadmin", "crm-admin"]) };
const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString();
const history = (createdAt: string) => ({ available: true, reason: null, generated_at: createdAt, backups: [
  { created_at: createdAt, source: "daily-20260928", database_bytes: 1048576, attachments_bytes: 2097152, verified: true },
] });
const lastRun = (result: string, error: string | null = null) => ({
  trigger: "scheduled", label: "daily-20260928", started_at: hoursAgo(1), finished_at: result === "running" ? null : hoursAgo(1), result, error,
});
const runStatus = (overrides: Record<string, unknown>) => ({
  available: true, reason: null, last_run: null, pending_request: false, pending_since: null, manual_available: true, ...overrides,
});
