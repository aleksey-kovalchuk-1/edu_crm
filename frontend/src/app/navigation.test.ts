import { describe, expect, it } from "vitest";
import { ROLES } from "../lib/user";
import { navGroups, pages, paths, settingsPages, visiblePages } from "./navigation";

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
  it("includes university management in settings and keeps Аккаунт last", () => {
    expect(settingsPages.map((p) => p.name)).toEqual([
      "Личный профиль",
      "Организация",
      "Учебные заведения",
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
    expect(new Set(settingsPaths).size).toBe(9);
    expect(settingsPaths.every((p) => p.startsWith("/settings/"))).toBe(true);
  });
});

describe("menu groups", () => {
  const allRoles = [ROLES.user, ROLES.supervisor, ROLES.admin, ROLES.superadmin];

  it("puts every visible page in exactly one group", () => {
    const grouped = navGroups(allRoles).flatMap((g) => g.pages.map((p) => p.path));
    expect([...grouped].sort()).toEqual(visiblePages(allRoles).map((p) => p.path).sort());
    expect(new Set(grouped).size).toBe(grouped.length);
  });

  it("keeps the current order of pages inside each group", () => {
    const order = pages.map((p) => p.path);
    for (const g of navGroups(allRoles)) {
      const idx = g.pages.map((p) => order.indexOf(p.path));
      expect(idx).toEqual([...idx].sort((a, b) => a - b));
    }
  });

  it("labels the groups Работа, Анализ, Данные клиентов, Администрирование, with Настройки in the last", () => {
    const groups = navGroups(allRoles);
    expect(groups.map((g) => g.label)).toEqual(["Работа", "Анализ", "Данные клиентов", "Администрирование"]);
    expect(groups.map((g) => g.hasSettings)).toEqual([false, false, false, true]);
  });

  it("shows a manager the pages their role allows, grouped", () => {
    const names = Object.fromEntries(navGroups([ROLES.user]).map((g) => [g.label, g.pages.map((p) => p.name)]));
    expect(names).toEqual({
      "Работа": ["Обзор", "Учебные заведения", "Договоры", "Взаимодействия", "Задачи"],
      "Анализ": ["Аналитика", "Отчёты"],
      "Администрирование": ["Справочники"],
    });
  });

  it("no longer lists the archived customer-data pages", () => {
    const names = navGroups(allRoles).flatMap((g) => g.pages.map((p) => p.name));
    for (const archived of ["Слушатели", "Компании", "Заявки на курсы", "Загрузка данных"]) {
      expect(names).not.toContain(archived);
    }
    expect(names).toContain("Проверка сигналов");
  });

  it("drops a group whose pages are all hidden, but keeps Администрирование for Настройки", () => {
    const groups = navGroups(["no-such-role"]);
    expect(groups.find((g) => g.id === "admin")?.hasSettings).toBe(true);
    expect(groups.every((g) => g.pages.length > 0 || g.hasSettings)).toBe(true);
  });
});
