import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const snapshot = {
  period_from: "2026-01-01",
  period_to: "2026-09-30",
  time_zone: "Europe/Moscow",
  universities: ["Все вузы"],
  stages: [
    { name: "Первый контакт", count: 2 }, { name: "Документы", count: 2 },
    { name: "Внедрение", count: 1 }, { name: "Обучение", count: 1 },
    { name: "Сопровождение", count: 0 },
  ],
  monthly: [{ month: "2026-01", count: 1 }, { month: "2026-02", count: 0 }, { month: "2026-03", count: 2 }],
  ranking: [{ id: 1, name: "Колледж связи", programs: 2, students: 24 }],
  has_stage_data: true,
  has_implementation_data: true,
};

describe("new interaction analytics", () => {
  it("shows four blocks in order and the current-year default period", async () => {
    const api = mockApi({ "GET /analytics/interactions": () => snapshot });
    renderApp("/analytics");

    expect(await screen.findByRole("heading", { name: "Вузы по этапам" })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 2 }).map((node) => node.textContent)).toEqual([
      "Параметры аналитики", "Вузы по этапам", "Внедрённые программы по месяцам", "Рейтинг вузов",
    ]);
    const params = new URLSearchParams(api.callsTo("GET", "/analytics/interactions")[0].path.split("?")[1]);
    const today = new Date();
    expect(params.get("period_from")).toBe(`${today.getFullYear()}-01-01`);
    expect(params.get("period_to")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(params.get("time_zone")).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
    expect(screen.getByText(/Часовой пояс браузера/)).toBeTruthy();
    expect(screen.queryByText("Показатели по годам")).toBeNull();
  });

  it("applies multiple universities to the charts and the PDF link", async () => {
    const api = mockApi({ "GET /analytics/interactions": () => snapshot });
    renderApp("/analytics");
    await screen.findByRole("heading", { name: "Вузы по этапам" });
    const options = within(screen.getByRole("group", { name: "Вузы" }));
    fireEvent.click(await options.findByLabelText("КС"));
    fireEvent.click(options.getByLabelText("Технический университет"));

    await waitFor(() => {
      const calls = api.callsTo("GET", "/analytics/interactions");
      const query = new URLSearchParams(calls.at(-1)?.path.split("?")[1]);
      expect(query.getAll("university_id")).toEqual(["1", "2"]);
    });
    const pdf = screen.getByRole("link", { name: "Скачать PDF" });
    const query = new URLSearchParams(pdf.getAttribute("href")!.split("?")[1]);
    expect(query.getAll("university_id")).toEqual(["1", "2"]);
    expect(pdf.getAttribute("href")).toContain("/api/v1/analytics/interactions.pdf?");
  });

  it("rejects an inverted period before requesting data or allowing PDF download", async () => {
    const api = mockApi({ "GET /analytics/interactions": () => snapshot });
    renderApp("/analytics");
    await screen.findByRole("heading", { name: "Вузы по этапам" });
    const requestsBefore = api.callsTo("GET", "/analytics/interactions").length;
    fireEvent.change(screen.getByLabelText("Период с"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Период по"), { target: { value: "2026-09-01" } });

    expect(screen.getByRole("alert").textContent).toContain("Конец периода раньше начала");
    expect(screen.queryByRole("link", { name: "Скачать PDF" })).toBeNull();
    expect(api.callsTo("GET", "/analytics/interactions")).toHaveLength(requestsBefore);
  });

  it("shows a clear empty state for each chart with no recorded events", async () => {
    mockApi({ "GET /analytics/interactions": () => ({
      ...snapshot,
      stages: snapshot.stages.map((stage) => ({ ...stage, count: 0 })),
      monthly: snapshot.monthly.map((month) => ({ ...month, count: 0 })),
      ranking: [], has_stage_data: false, has_implementation_data: false,
    }) });
    renderApp("/analytics");

    expect(await screen.findAllByText("Нет данных за выбранный период")).toHaveLength(3);
  });

  it("blocks periods longer than ten years before querying or downloading", async () => {
    const api = mockApi({ "GET /analytics/interactions": () => snapshot });
    renderApp("/analytics");
    await screen.findByRole("heading", { name: "Вузы по этапам" });
    const requestsBefore = api.callsTo("GET", "/analytics/interactions").length;
    fireEvent.change(screen.getByLabelText("Период с"), { target: { value: "2015-01-01" } });
    fireEvent.change(screen.getByLabelText("Период по"), { target: { value: "2026-01-01" } });
    expect(screen.getByRole("alert").textContent).toContain("10 лет");
    expect(screen.queryByRole("link", { name: "Скачать PDF" })).toBeNull();
    expect(api.callsTo("GET", "/analytics/interactions")).toHaveLength(requestsBefore);
  });

  it("qualifies a recorded zero students value", async () => {
    mockApi({ "GET /analytics/interactions": () => ({
      ...snapshot, ranking: [{ id: 1, name: "Колледж связи", programs: 2, students: 0 }],
    }) });
    renderApp("/analytics");
    const group = await screen.findByRole("listitem", { name: /Колледж связи: 2 внедрённых программ/ });
    expect(group.getAttribute("aria-label")).toContain("0 студентов (возможно, данные не заполнены)");
    expect(group.textContent).toContain("0*");
    expect(screen.getByText(/0 может означать незаполненные данные/)).toBeTruthy();
  });
});
