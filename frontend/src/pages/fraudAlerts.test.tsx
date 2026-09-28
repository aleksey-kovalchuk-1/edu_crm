import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
    // The learner, application and supplier pages are archived: the alert names the record without a dead link.
    expect(await screen.findByText(/Анкета #\d+ · раздел в архиве/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Открыть анкету/ })).toBeNull();
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

  it("only offers valid next review states for a cleared signal", async () => {
    const cleared = { ...alert, status: "cleared", resolution_code: "false_positive" };
    mockApi({
      "GET /fraud-alerts": () => [cleared],
      "GET /fraud-alerts/status": () => ({ document_match: "active", rule_version: 1,
        batch_row_limit: 500, hourly_import_limit: 10 }),
      "GET /fraud-alerts/8": () => cleared,
    });
    renderApp("/fraud-alerts");
    fireEvent.click(await screen.findByRole("button", { name: /Сигнал 8/ }));
    const decision = await screen.findByLabelText("Решение");
    expect(within(decision).getByRole("option", { name: "На проверке" })).toBeTruthy();
    expect(within(decision).queryByRole("option", { name: "Открыт" })).toBeNull();
    expect(within(decision).queryByRole("option", { name: "Подтверждён проверкой" })).toBeNull();
  });
});
