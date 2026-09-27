import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../test/utils";

afterEach(() => vi.unstubAllEnvs());

describe("environment labels", () => {
  it("hides the demo disclaimer on the public deployment", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "false");
    mockApi();
    renderApp("/");
    await screen.findByRole("heading");
    expect(screen.queryByText("Демонстрационный контур")).toBeNull();
    expect(screen.queryByText("Рабочий шаблон · Данные вымышлены")).toBeNull();
  });

  it("shows the demo disclaimer in the local demo", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "true");
    mockApi();
    renderApp("/");
    await screen.findByRole("heading");
    expect(screen.getByText("Демонстрационный контур")).toBeTruthy();
    expect(screen.getByText("Рабочий шаблон · Данные вымышлены")).toBeTruthy();
  });
});
