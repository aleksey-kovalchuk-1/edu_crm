import { describe, expect, it } from "vitest";
import { ROLES } from "../lib/user";
import { pages, paths, settingsPages } from "./navigation";

describe("sidebar placement", () => {
  it("keeps Процессы (workflows) as the last non-hidden entry in pages", () => {
    // The «Настройки» menu is placed directly after the last flat sidebar NavLink
    // (Layout.tsx renders it as the next sibling of the visiblePages() list). That
    // placement — and the App.test.tsx adjacency test for it — silently depends on
    // Процессы staying last among the non-hidden pages. Pin it here so a future page
    // added after it in `pages` fails loudly instead of quietly reordering the sidebar.
    const visible = pages.filter((p) => !p.hidden);
    expect(visible[visible.length - 1].path).toBe(paths.workflows);
  });
});

describe("settings navigation data", () => {
  it("lists the seven originally required settings pages in order, plus Аккаунт last", () => {
    // The first seven keep the exact order from the original spec; «Аккаунт» (logout + account
    // overview) was added afterward and deliberately appended rather than inserted, so it never
    // disturbs that fixed order.
    expect(settingsPages.map((p) => p.name)).toEqual([
      "Личный профиль",
      "Организация",
      "Уведомления",
      "Безопасность",
      "Пользователи и роли",
      "Персональные данные",
      "Резервное копирование",
      "Аккаунт",
    ]);
  });

  it("marks every settings page hidden from the flat sidebar list", () => {
    expect(settingsPages.every((p) => p.hidden)).toBe(true);
  });

  it("gates Пользователи и роли and Резервное копирование to superadmin only", () => {
    const users = settingsPages.find((p) => p.name === "Пользователи и роли")!;
    const backups = settingsPages.find((p) => p.name === "Резервное копирование")!;
    expect(users.roles).toEqual([ROLES.superadmin]);
    expect(backups.roles).toEqual([ROLES.superadmin]);
  });

  it("leaves the other settings pages (including Аккаунт) open to every role", () => {
    const open = settingsPages.filter((p) => !["Пользователи и роли", "Резервное копирование"].includes(p.name));
    expect(open.every((p) => p.roles === undefined)).toBe(true);
  });

  it("gives every settings page a distinct path under /settings", () => {
    const settingsPaths = settingsPages.map((p) => p.path);
    expect(new Set(settingsPaths).size).toBe(8);
    expect(settingsPaths.every((p) => p.startsWith("/settings/"))).toBe(true);
  });
});
