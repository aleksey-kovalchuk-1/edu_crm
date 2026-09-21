import { describe, expect, it } from "vitest";
import { ROLES } from "../lib/user";
import { paths, settingsPages } from "./navigation";

describe("settings navigation data", () => {
  it("lists the seven settings pages in the required order", () => {
    expect(settingsPages.map((p) => p.name)).toEqual([
      "Личный профиль",
      "Организация",
      "Уведомления",
      "Безопасность",
      "Пользователи и роли",
      "Персональные данные",
      "Резервное копирование",
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

  it("leaves the other five settings pages open to every role", () => {
    const open = settingsPages.filter((p) => !["Пользователи и роли", "Резервное копирование"].includes(p.name));
    expect(open.every((p) => p.roles === undefined)).toBe(true);
  });

  it("gives every settings page a distinct path under /settings", () => {
    const settingsPaths = settingsPages.map((p) => p.path);
    expect(new Set(settingsPaths).size).toBe(7);
    expect(settingsPaths.every((p) => p.startsWith("/settings/"))).toBe(true);
  });
});
