import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp } from "../test/utils";

const signedOut = () => apiError(401, "UNAUTHENTICATED", "Требуется вход в систему");

describe("organization name in the brand", () => {
  it("shows the organization name under UniCRM in the sidebar", async () => {
    mockApi();
    renderApp("/");
    const brand = await screen.findByRole("link", { name: /UniCRM/ });
    await within(brand).findByText("ИТ Школа Ростелеком");
  });

  it("shows the organization name on the login screen before sign-in", async () => {
    mockApi({ "GET /auth/me": signedOut });
    renderApp("/?auth_error=NO_ACCESS");
    await screen.findByRole("button", { name: /Войти через Keycloak/ });
    await screen.findByText("ИТ Школа Ростелеком");
  });

  it("keeps the login screen working when the name cannot be loaded", async () => {
    mockApi({
      "GET /auth/me": signedOut,
      "GET /organization/brand": () => apiError(503, "SERVICE_UNAVAILABLE", "Недоступно"),
    });
    renderApp("/?auth_error=NO_ACCESS");
    await screen.findByRole("button", { name: /Войти через Keycloak/ });
    expect(screen.queryByText("ИТ Школа Ростелеком")).toBeNull();
    expect(screen.queryByText(/Недоступно/)).toBeNull();
  });
});
