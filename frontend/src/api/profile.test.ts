import { describe, expect, it } from "vitest";
import { contactStatus, isPlausiblePhone } from "./profile";

describe("profile helpers", () => {
  it("never calls a saved handle a connected integration", () => {
    expect(contactStatus("")).toBe("Не указан");
    expect(contactStatus("   ")).toBe("Не указан");
    expect(contactStatus("anna_demo")).toBe("Сохранён · не подключён");
  });

  it("accepts only Russian mobile numbers for SMS verification", () => {
    expect(isPlausiblePhone("+7 999 123-45-67")).toBe(true);
    expect(isPlausiblePhone("89991234567")).toBe(true);
    expect(isPlausiblePhone("+7 495 123-45-67")).toBe(false);
    expect(isPlausiblePhone("12345")).toBe(false);
  });
});
