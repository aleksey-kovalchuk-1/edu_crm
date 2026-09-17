import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const COLUMNS = [
  { key: "university", label: "Университет" },
  { key: "program", label: "Программа" },
  { key: "status", label: "Статус" },
];

describe("reports", () => {
  it("submits chosen filters and format, then shows a download link once the job succeeds", async () => {
    let job: Record<string, unknown> | null = null;
    const api = mockApi({
      "GET /reports/columns": () => COLUMNS,
      "GET /reports": () => (job ? [job] : []),
      "POST /reports": (call) => {
        job = { id: 7, status: "succeeded", format: (call.body as { format: string }).format, created_at: "2026-09-17T10:00:00Z", finished_at: "2026-09-17T10:00:01Z" };
        return [202, job];
      },
    });

    renderApp("/reports");
    await screen.findByText("Параметры отчёта");
    expect(screen.getByText("Отчётов пока нет.")).toBeTruthy();

    fireEvent.click(screen.getByRole("radio", { name: "PDF" }));
    fireEvent.click(screen.getByRole("button", { name: "Сформировать отчёт" }));

    await waitFor(() => expect(api.count("POST", "/reports")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/reports")?.body).toMatchObject({
      format: "pdf",
      university_ids: [],
      columns: [],
    });

    expect(await screen.findByRole("link", { name: "Скачать" })).toBeTruthy();
    expect(screen.getByText("Готов")).toBeTruthy();
  });
});
