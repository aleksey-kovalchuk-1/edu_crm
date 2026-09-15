import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AuditEvent } from "../api/types";
import { AUDIT_PATH, mockApi, renderApp, sessionFixture } from "../test/utils";

const events = (): AuditEvent[] => [
  {
    id: 2,
    // 5.5 min: the panel's clock is read at mount, slightly before this is fetched.
    occurred_at: new Date(Date.now() - 5.5 * 60_000).toISOString(),
    action: "task.update",
    entity_type: "task",
    entity_id: 1,
    summary: "Задача «Согласовать договор» отмечена выполненной",
    user: { id: 2, full_name: "Олег Кузнецов" },
  },
  {
    id: 1,
    occurred_at: "2024-01-15T09:30:00Z",
    action: "university.create",
    entity_type: "university",
    entity_id: 1,
    summary: "Добавлено учебное заведение «Колледж связи»",
    user: null,
  },
];

const panel = async () =>
  (await screen.findByRole("heading", { name: "Последние действия" })).closest(
    "section",
  ) as HTMLElement;

describe("recent actions", () => {
  it("lists events with author and time for supervisors", async () => {
    mockApi({ [`GET ${AUDIT_PATH}`]: events });
    renderApp("/");
    const section = await panel();
    const items = await within(section).findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("отмечена выполненной");
    expect(within(items[0]).getByText("Олег Кузнецов")).toBeTruthy();
    expect(within(items[0]).getByText("5 мин назад")).toBeTruthy();
    expect(within(items[1]).getByText("Система")).toBeTruthy();
    expect(items[1].querySelector("time")?.textContent).toMatch(/2024/);
  });

  it("hides the author for a crm-user", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"]),
      [`GET ${AUDIT_PATH}`]: events,
    });
    renderApp("/");
    const section = await panel();
    await within(section).findAllByRole("listitem");
    expect(within(section).queryByText("Олег Кузнецов")).toBeNull();
    expect(within(section).getByText("Ваши изменения")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    mockApi();
    renderApp("/");
    expect(await within(await panel()).findByText("Действий пока нет.")).toBeTruthy();
  });

  it("is refreshed after a successful task toggle", async () => {
    const api = mockApi({
      "PATCH /tasks/1": () => ({ ...api.data.tasks[0], done: true }),
    });
    renderApp("/");
    await within(await panel()).findByText("Действий пока нет.");
    expect(api.count("GET", AUDIT_PATH)).toBe(1);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Согласовать договор" }));
    await waitFor(() => expect(api.count("GET", AUDIT_PATH)).toBe(2));
  });
});
