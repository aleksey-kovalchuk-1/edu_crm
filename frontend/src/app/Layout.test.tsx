import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

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

describe("shell", () => {
  it("keeps «Выйти» and the profile link in the top bar", async () => {
    mockApi();
    renderApp("/");
    const banner = await screen.findByRole("banner");
    expect(within(banner).getByRole("button", { name: "Выйти" })).toBeTruthy();
    expect(within(banner).getByRole("link", { name: /Анна Петрова/ })).toBeTruthy();
  });

  it("labels the menu groups for a supervisor", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-supervisor"]) });
    renderApp("/");
    const nav = await screen.findByRole("navigation");
    for (const name of ["Работа", "Анализ", "Данные клиентов", "Администрирование"]) {
      expect(within(nav).getByRole("group", { name })).toBeTruthy();
    }
  });

  it("opens and closes the phone menu with the menu button and Escape", async () => {
    mockApi();
    renderApp("/");
    const button = await screen.findByRole("button", { name: "Меню" });
    const menu = document.getElementById(button.getAttribute("aria-controls")!)!;
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(menu.className).toContain("mobile-open");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(menu.className).not.toContain("mobile-open");
  });

  it("moves focus into the phone menu when it opens and back to the menu button on Escape", async () => {
    mockApi();
    renderApp("/");
    const button = await screen.findByRole("button", { name: "Меню" });
    fireEvent.click(button);
    const menu = document.getElementById("app-menu")!;
    expect(menu.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(button);
  });
});

