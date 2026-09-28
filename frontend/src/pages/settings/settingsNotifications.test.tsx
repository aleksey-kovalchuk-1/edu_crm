import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../../test/utils";

const ev = (key: string, label: string, enabled: boolean) => ({ key, label, enabled, default: enabled });
const prefs = (paused_until: string | null = null) => ({
  paused_until,
  groups: [
    { key: "universities", label: "Вузы", events: [ev("university_assigned", "Вас назначили ответственным за вуз", true), ev("university_contacts_changed", "Изменили контакты закреплённого за вами вуза", false)] },
    { key: "launches", label: "Взаимодействия с вузами", events: [ev("launch_stage_changed", "Изменили этап взаимодействия по вашему вузу", false)] },
    { key: "tasks", label: "Задачи", events: [ev("task_assigned", "Вас назначили исполнителем или соисполнителем задачи", true)] },
    { key: "contracts", label: "Договоры и лицензии", events: [ev("contract_signed", "Подписали договор по вашему вузу", false)] },
  ],
});

describe("settings notifications", () => {
  it("shows the four groups with checkbox states from the server", async () => {
    mockApi({ "GET /notifications/preferences": () => prefs() });
    renderApp("/settings/notifications");
    for (const name of ["Вузы", "Взаимодействия с вузами", "Задачи", "Договоры и лицензии"]) await screen.findByRole("group", { name });
    expect((screen.getByLabelText("Вас назначили ответственным за вуз") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Подписали договор по вашему вузу") as HTMLInputElement).checked).toBe(false);
  });

  it("saves only the changed checkboxes and confirms", async () => {
    const api = mockApi({
      "GET /notifications/preferences": () => prefs(),
      "PUT /notifications/preferences": () => prefs(),
    });
    renderApp("/settings/notifications");
    fireEvent.click(await screen.findByLabelText("Подписали договор по вашему вузу"));
    fireEvent.click(screen.getByLabelText("Вас назначили исполнителем или соисполнителем задачи"));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("Настройки сохранены");
    expect(api.callsTo("PUT", "/notifications/preferences")[0].body).toEqual({
      preferences: { contract_signed: true, task_assigned: false },
    });
  });

  it("pauses for the chosen duration and shows until when", async () => {
    const api = mockApi({
      "GET /notifications/preferences": () => prefs(),
      // Relative to now: a fixed date would eventually be in the past and read as "no pause".
      "PUT /notifications/pause": () => ({ paused_until: new Date(Date.now() + 24 * 3600_000).toISOString() }),
    });
    renderApp("/settings/notifications");
    fireEvent.change(await screen.findByLabelText("Длительность паузы"), { target: { value: "tomorrow" } });
    fireEvent.click(screen.getByRole("button", { name: "Приостановить все уведомления" }));
    await screen.findByText(/Уведомления приостановлены до/);
    expect(api.callsTo("PUT", "/notifications/pause")[0].body).toEqual({ duration: "tomorrow" });
  });

  it("shows an indefinite pause and resumes notifications", async () => {
    const api = mockApi({
      "GET /notifications/preferences": () => prefs("9999-12-31T00:00:00Z"),
      "PUT /notifications/pause": () => ({ paused_until: null }),
    });
    renderApp("/settings/notifications");
    await screen.findByText("Уведомления приостановлены до выключения паузы");
    fireEvent.click(screen.getByRole("button", { name: "Возобновить уведомления" }));
    await waitFor(() => expect(api.callsTo("PUT", "/notifications/pause")[0].body).toEqual({ duration: "off" }));
  });
});
