import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { UserRound } from "lucide-react";
import { SettingsMenu } from "./SettingsMenu";
import type { PageMeta } from "./navigation";

const PAGES: PageMeta[] = [
  { path: "/settings/a", name: "Пункт А", icon: UserRound, heading: "А", subtitle: "", create: null, hidden: true },
  { path: "/settings/b", name: "Пункт Б", icon: UserRound, heading: "Б", subtitle: "", create: null, hidden: true },
  { path: "/settings/c", name: "Только для суперадмина", icon: UserRound, heading: "В", subtitle: "", create: null, hidden: true, roles: ["crm-superadmin"] },
];

function renderMenu(props: Partial<React.ComponentProps<typeof SettingsMenu>> = {}) {
  return render(
    <MemoryRouter>
      <SettingsMenu pages={PAGES} currentPath="/" userRoles={["crm-user"]} {...props} />
    </MemoryRouter>,
  );
}

describe("SettingsMenu", () => {
  it("does not render the submenu until opened", () => {
    renderMenu();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("opens on hover and closes when the pointer leaves the whole menu area", async () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    fireEvent.mouseEnter(trigger.closest("[data-settings-menu-root]")!);
    expect(await screen.findByRole("menu")).toBeTruthy();
    fireEvent.mouseLeave(trigger.closest("[data-settings-menu-root]")!);
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("moving the pointer from the trigger into the panel does not close it (no dead zone)", async () => {
    renderMenu();
    const root = screen.getByRole("button", { name: /Настройки/ }).closest("[data-settings-menu-root]")!;
    fireEvent.mouseEnter(root);
    const panel = await screen.findByRole("menu");
    // Leaving the trigger sub-area but staying within the shared root must not close the menu:
    fireEvent.mouseLeave(screen.getByRole("button", { name: /Настройки/ }));
    fireEvent.mouseEnter(panel);
    expect(screen.getByRole("menu")).toBeTruthy();
  });

  it("opens and closes on click, independent of hover", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.click(trigger);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when a click lands outside the whole menu area", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("is keyboard operable: Enter opens, Escape closes and returns focus to the trigger", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("ArrowDown from the trigger moves focus into the first menu item", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const items = screen.getAllByRole("menuitem");
    expect(document.activeElement).toBe(items[0]);
  });

  it("filters items by role — a plain crm-user never sees the superadmin-only item", () => {
    renderMenu({ userRoles: ["crm-user"] });
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    expect(screen.queryByRole("menuitem", { name: /Только для суперадмина/ })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Пункт А" })).toBeTruthy();
  });

  it("shows the superadmin-only item for a superadmin", () => {
    renderMenu({ userRoles: ["crm-superadmin"] });
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    expect(screen.getByRole("menuitem", { name: /Только для суперадмина/ })).toBeTruthy();
  });

  it("shows the trigger as active when the current path matches any item", () => {
    renderMenu({ currentPath: "/settings/a" });
    expect(screen.getByRole("button", { name: /Настройки/ }).className).toContain("active");
  });

  it("lists items in the exact order given", () => {
    renderMenu({ userRoles: ["crm-superadmin"] });
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    const items = screen.getAllByRole("menuitem").map((el) => el.textContent);
    expect(items).toEqual(["Пункт А", "Пункт Б", "Только для суперадмина"]);
  });
});
