import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { UserRound } from "lucide-react";
import { SettingsMenu } from "./SettingsMenu";
import type { PageMeta } from "./navigation";

const PAGES: PageMeta[] = [
  { path: "/settings/a", name: "Пункт А", icon: UserRound, heading: "А", subtitle: "", create: null, hidden: true },
  { path: "/settings/b", name: "Пункт Б", icon: UserRound, heading: "Б", subtitle: "", create: null, hidden: true },
  { path: "/settings/c", name: "Только для суперадмина", icon: UserRound, heading: "В", subtitle: "", create: null, hidden: true, roles: ["crm-superadmin"] },
];

function renderMenu(path = "/", props: Partial<React.ComponentProps<typeof SettingsMenu>> = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SettingsMenu pages={PAGES} currentPath={path} userRoles={["crm-user"]} {...props} />
    </MemoryRouter>,
  );
}
const trigger = () => screen.getByRole("button", { name: /Настройки/ });

describe("SettingsMenu", () => {
  it("is collapsed outside settings pages", () => {
    renderMenu("/");
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("link", { name: "Пункт А" })).toBeNull();
  });

  it("opens on click and stays open without hover", () => {
    renderMenu("/");
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    fireEvent.mouseLeave(trigger());
    expect(screen.getByRole("link", { name: "Пункт А" })).toBeTruthy();
  });

  it("a tap (hover then click) opens the group and leaves it open", () => {
    renderMenu("/");
    fireEvent.mouseEnter(trigger());
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("link", { name: "Пункт Б" })).toBeTruthy();
  });

  it("closes on a second click", () => {
    renderMenu("/");
    fireEvent.click(trigger());
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
  });

  it("is open on a settings page and marks the current item", () => {
    renderMenu("/settings/b");
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("link", { name: "Пункт Б" }).getAttribute("aria-current")).toBe("page");
    expect(trigger().className).toContain("active");
  });

  it("hides items the role may not see", () => {
    renderMenu("/settings/a");
    expect(screen.queryByRole("link", { name: "Только для суперадмина" })).toBeNull();
  });

  it("shows superadmin-only items to a superadmin", () => {
    renderMenu("/settings/a", { userRoles: ["crm-superadmin"] });
    expect(screen.getByRole("link", { name: "Только для суперадмина" })).toBeTruthy();
  });

  it("calls onNavigate when an item is chosen", () => {
    const onNavigate = vi.fn();
    renderMenu("/", { onNavigate });
    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole("link", { name: "Пункт А" }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it("links the button to the list it controls", () => {
    renderMenu("/settings/a");
    const list = document.getElementById(trigger().getAttribute("aria-controls")!);
    expect(list?.tagName).toBe("UL");
  });
});
