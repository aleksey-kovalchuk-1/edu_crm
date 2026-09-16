import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const columnTitles = () =>
  screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

describe("status board", () => {
  it("groups launches by status of the default workflow, in position order", async () => {
    mockApi();
    renderApp("/interactions/board");
    await screen.findByText("ВЗ-0001");

    // The inactive "Архивный статус" holds no launches, so it is hidden.
    expect(columnTitles()).toEqual([
      "Первый контакт",
      "Согласование документов",
      "Сопровождение",
    ]);

    const documentsColumn = screen.getByText("Согласование документов").closest(".board-column")!;
    expect(documentsColumn.textContent).toContain("ВЗ-0001");
    const supportColumn = screen.getByText("Сопровождение").closest(".board-column")!;
    expect(supportColumn.textContent).toContain("ВЗ-0002");

    const emptyColumn = screen.getByText("Первый контакт").closest(".board-column")!;
    expect(emptyColumn.textContent).toContain("Нет взаимодействий");
  });

  it("shows an inactive status column when it currently holds a launch", async () => {
    const api = mockApi();
    api.data.launches = api.data.launches.map((l) => (l.id === 1 ? { ...l, status_id: 13 } : l));
    renderApp("/interactions/board");
    await screen.findByText("ВЗ-0001");

    expect(columnTitles()).toEqual([
      "Первый контакт",
      "Согласование документов",
      "Архивный статус",
      "Сопровождение",
    ]);
    const archiveColumn = screen.getByText("Архивный статус").closest(".board-column")!;
    expect(archiveColumn.textContent).toContain("ВЗ-0001");
  });

  it("links each card to the interaction detail page", async () => {
    mockApi();
    renderApp("/interactions/board");
    const card = await screen.findByRole("link", { name: /Аналитика данных/ });
    expect(card.getAttribute("href")).toBe("/interactions/1");
  });
});
