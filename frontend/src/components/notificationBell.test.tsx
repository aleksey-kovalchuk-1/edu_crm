import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const item = (overrides: Record<string, unknown> = {}) => ({
  id: 1, event_type: "task_assigned", title: "Вас назначили исполнителем задачи", body: "Подготовить договор",
  link: { type: "task", id: 5, path: "/tasks/5" }, created_at: "2026-09-27T10:00:00Z", read_at: null, ...overrides,
});

describe("notification bell", () => {
  it("is neutral without unread notifications", async () => {
    mockApi();
    renderApp("/");
    const bell = await screen.findByRole("button", { name: "Уведомления" });
    expect(bell.className).not.toContain("has-unread");
    expect(within(bell).queryByTestId("unread-count")).toBeNull();
  });

  it("is highlighted with the unread count", async () => {
    mockApi({ "GET /notifications/unread-count": () => ({ count: 3 }) });
    renderApp("/");
    const bell = await screen.findByRole("button", { name: "Уведомления: 3 непрочитанных" });
    expect(bell.className).toContain("has-unread");
    expect(within(bell).getByTestId("unread-count").textContent).toBe("3");
  });

  it("opens a list; clicking an item marks it read and follows its link", async () => {
    const api = mockApi({
      "GET /notifications/unread-count": () => ({ count: 1 }),
      "GET /notifications": () => [item()],
      "POST /notifications/1/read": () => [204, null],
    });
    renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: /Уведомления/ }));
    fireEvent.click(await screen.findByRole("link", { name: /Вас назначили исполнителем задачи/ }));
    await waitFor(() => expect(api.callsTo("POST", "/notifications/1/read")).toHaveLength(1));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toContain("/tasks/5"));
  });

  it("shows a notification without a link as plain text and marks all read", async () => {
    const api = mockApi({
      "GET /notifications/unread-count": () => ({ count: 1 }),
      "GET /notifications": () => [item({ id: 2, event_type: "university_unassigned", title: "Вас сняли с ответственности за вуз", link: null })],
      "POST /notifications/read-all": () => [204, null],
    });
    renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: /Уведомления/ }));
    await screen.findByText("Вас сняли с ответственности за вуз");
    expect(screen.queryByRole("link", { name: /Вас сняли/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Отметить все прочитанными" }));
    await waitFor(() => expect(api.callsTo("POST", "/notifications/read-all")).toHaveLength(1));
  });

  it("says so when there are no notifications", async () => {
    mockApi();
    renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: "Уведомления" }));
    await screen.findByText("Новых уведомлений нет");
  });
});
