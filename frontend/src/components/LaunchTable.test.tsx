import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { Launch } from "../api/types";
import { LaunchTable } from "./LaunchTable";

const launch = {
  id: 1, university_id: 1, university: "Колледж связи", city: "Москва", program: "Аналитика данных",
  product: "Python", owner: "Анна Петрова", students: 12, deadline: "2026-10-03", stage: 1, overdue: false,
} as unknown as Launch;

describe("LaunchTable", () => {
  it("labels every data cell with its column name for the stacked phone layout", () => {
    render(<MemoryRouter><LaunchTable rows={[launch]} stages={["Первый контакт", "Документы"]} /></MemoryRouter>);
    const table = screen.getByRole("table");
    expect(table.className).toContain("stack-table");
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    const cells = within(table).getAllByRole("cell");
    expect(cells.map((c) => c.getAttribute("data-label"))).toEqual(headers.map((h) => h || null));
  });
});
