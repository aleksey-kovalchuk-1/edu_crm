import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

const alert = {
  id: 8, rule_code: "document_identifier_reuse", rule_version: 1, evidence_kind: "snils",
  priority: "high", status: "open", entity_type: "learner", entity_id: 7,
  related_entity_id: 9, batch_id: 4, row_number: 2,
  created_at: "2026-09-26T12:00:00Z", updated_at: "2026-09-26T12:00:00Z",
  reviewed_by_user_id: null, reviewed_at: null, resolution_code: null,
};

describe("fraud review", () => {
  it("filters and resolves a safe alert with a link to its card", async () => {
    const api = mockApi({
      "GET /fraud-alerts": () => [alert],
      "GET /fraud-alerts/status": () => ({ document_match: "active", rule_version: 1,
        batch_row_limit: 500, hourly_import_limit: 10 }),
      "GET /fraud-alerts/8": () => alert,
      "PATCH /fraud-alerts/8": () => ({ ...alert, status: "cleared", resolution_code: "false_positive" }),
    });
    renderApp("/fraud-alerts");
    expect(await screen.findByText(/Повтор документа/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Статус"), { target: { value: "open" } });
    await waitFor(() => expect(api.calls.some((call) => call.path.includes("status=open"))).toBe(true));
    fireEvent.click(await screen.findByRole("button", { name: /Сигнал 8/ }));
    expect(await screen.findByRole("link", { name: /Открыть анкету/ })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Решение"), { target: { value: "cleared" } });
    fireEvent.change(screen.getByLabelText("Причина"), { target: { value: "false_positive" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить решение" }));
    await waitFor(() => expect(api.count("PATCH", "/fraud-alerts/8")).toBe(1));
    expect(api.calls.find((call) => call.method === "PATCH")?.body).toMatchObject({
      expected_updated_at: alert.updated_at, status: "cleared", resolution_code: "false_positive",
    });
    expect(screen.queryByText("001-234-567 89")).toBeNull();
  });

  it("does not request the queue for a regular user", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/fraud-alerts");
    expect(await screen.findByText(/доступна руководителю/)).toBeTruthy();
    expect(api.count("GET", "/fraud-alerts")).toBe(0);
  });
});
