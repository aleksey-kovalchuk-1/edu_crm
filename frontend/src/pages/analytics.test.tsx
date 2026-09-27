import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

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
    expect(params.get("time_zone")).toBe("Europe/Moscow");
    expect(screen.getByText(/Часовой пояс профиля: Europe\/Moscow/)).toBeTruthy();
    expect(screen.queryByText("Показатели по годам")).toBeNull();
    expect(screen.queryByText("Период и вузы применяются ко всем трём графикам и PDF.")).toBeNull();
  });

  it("falls back to the browser timezone only when the profile has no timezone", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-supervisor"], undefined, { timezone: "" }),
      "GET /analytics/interactions": () => snapshot,
    });
    renderApp("/analytics");
    await screen.findByRole("heading", { name: "Вузы по этапам" });
    const params = new URLSearchParams(api.callsTo("GET", "/analytics/interactions")[0].path.split("?")[1]);
    expect(params.get("time_zone")).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
    expect(screen.getByText(/Часовой пояс браузера/)).toBeTruthy();
  });

  it("applies multiple universities to the charts and the PDF link", async () => {
    const api = mockApi({ "GET /analytics/interactions": () => snapshot });
    renderApp("/analytics");
    await screen.findByRole("heading", { name: "Вузы по этапам" });
    fireEvent.click(screen.getByRole("button", { name: /Вузы: Все вузы/ }));
    const options = within(screen.getByRole("group", { name: "Вузы" }));
    fireEvent.click(await options.findByLabelText("КС"));
    fireEvent.click(options.getByLabelText("Технический университет"));

    await waitFor(() => {
      const calls = api.callsTo("GET", "/analytics/interactions");
      const query = new URLSearchParams(calls.at(-1)?.path.split("?")[1]);
      expect(query.getAll("university_id")).toEqual(["1", "2"]);
    });
    const pdf = await screen.findByRole("link", { name: "Скачать PDF" });
    const query = new URLSearchParams(pdf.getAttribute("href")!.split("?")[1]);
    expect(query.getAll("university_id")).toEqual(["1", "2"]);
    expect(pdf.getAttribute("href")).toContain("/api/v1/analytics/interactions.pdf?");
  });

  it("filters universities by name and keeps the picker in the page flow", async () => {
    mockApi({ "GET /analytics/interactions": () => snapshot });
    renderApp("/analytics");
    fireEvent.click(await screen.findByRole("button", { name: /Вузы: Все вузы/ }));
    const picker = screen.getByRole("group", { name: "Вузы" });
    await within(picker).findByLabelText("КС");
    fireEvent.change(within(picker).getByRole("searchbox", { name: "Найти вуз" }), { target: { value: "Технический" } });
    expect(within(picker).queryByLabelText("КС")).toBeNull();
    expect(within(picker).getByLabelText("Технический университет")).toBeTruthy();
    fireEvent.click(within(picker).getByLabelText("Технический университет"));
    expect(screen.getByRole("button", { name: /Вузы: Технический университет/ })).toBeTruthy();
    expect(picker.className).toContain("analytics-university-picker");
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

  it("shows clearly marked example charts and a real-data flow when all actual charts are empty", async () => {
    mockApi({ "GET /analytics/interactions": () => ({
      ...snapshot,
      stages: snapshot.stages.map((stage) => ({ ...stage, count: 0 })),
      monthly: snapshot.monthly.map((month) => ({ ...month, count: 0 })),
      ranking: [], has_stage_data: false, has_implementation_data: false,
    }) });
    renderApp("/analytics");

    expect(await screen.findByText("Нет данных за выбранный период")).toBeTruthy();
    expect(screen.getByText(/демонстрационный пример/)).toBeTruthy();
    expect(screen.getByText(/Создайте взаимодействие/)).toBeTruthy();
    expect(screen.getByRole("img", { name: /Янв 2026 — 0/ })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Рейтинг вузов по внедрённым программам и студентам" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Скачать PDF" })).toBeNull();
    expect(screen.getByRole("button", { name: "Скачать PDF" }).hasAttribute("disabled")).toBe(true);
  });

  it("does not mix example values into a partially populated real snapshot", async () => {
    mockApi({ "GET /analytics/interactions": () => ({
      ...snapshot, monthly: snapshot.monthly.map((month) => ({ ...month, count: 0 })),
      ranking: [], has_implementation_data: false,
    }) });
    renderApp("/analytics");
    expect(await screen.findAllByText("Нет данных за выбранный период")).toHaveLength(2);
    expect(screen.queryByText(/демонстрационный пример/)).toBeNull();
    expect(screen.getByRole("link", { name: "Скачать PDF" })).toBeTruthy();
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
    const group = await screen.findByRole("listitem", { name: /Колледж связи: внедрённые программы — 2/ });
    expect(group.getAttribute("aria-label")).toContain("студенты — 0 (возможно, данные не заполнены)");
    expect(group.textContent).toContain("0*");
    expect(screen.getByText(/0 может означать незаполненные данные/)).toBeTruthy();
  });
});
