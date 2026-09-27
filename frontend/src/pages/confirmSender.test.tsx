import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp } from "../test/utils";

describe("confirm sender page", () => {
  it("works without a session and does nothing until the button is pressed", async () => {
    const api = mockApi({
      "GET /auth/me": () => apiError(401, "UNAUTHENTICATED", "Нужно войти"),
      "POST /email-senders/confirm": () => ({ email_address: "anna@uni-demo.ru" }),
    });
    renderApp("/confirm-sender?token=abc");
    await screen.findByRole("button", { name: "Подтвердить" });
    expect(api.callsTo("POST", "/email-senders/confirm")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await screen.findByText(/anna@uni-demo.ru подтверждён/);
    expect(api.callsTo("POST", "/email-senders/confirm")[0].body).toEqual({ token: "abc" });
  });

  it("shows the server message for an invalid link", async () => {
    mockApi({ "POST /email-senders/confirm": () => apiError(409, "CONFLICT", "Ссылка недействительна или устарела") });
    renderApp("/confirm-sender?token=bad");
    fireEvent.click(await screen.findByRole("button", { name: "Подтвердить" }));
    await screen.findByText(/Ссылка недействительна или устарела/);
  });

  it("explains a missing token", async () => {
    mockApi();
    renderApp("/confirm-sender");
    await screen.findByText(/В ссылке нет кода подтверждения/);
    expect(screen.queryByRole("button", { name: "Подтвердить" })).toBeNull();
  });
});
