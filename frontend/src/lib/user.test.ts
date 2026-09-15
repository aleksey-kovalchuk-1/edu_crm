import { describe, expect, it } from "vitest";
import { canEditCatalog, hasCrmAccess, roleLabel, userInitials } from "./user";

describe("user helpers", () => {
  it("labels the highest CRM role", () => {
    expect(roleLabel(["crm-user"])).toBe("Менеджер");
    expect(roleLabel(["crm-user", "crm-supervisor"])).toBe("Руководитель");
    expect(roleLabel(["crm-supervisor", "crm-admin", "crm-user"])).toBe("Администратор");
    expect(roleLabel(["offline_access"])).toBeNull();
    expect(hasCrmAccess([])).toBe(false);
  });

  it("allows catalog editing for supervisors and admins only", () => {
    expect(canEditCatalog(["crm-user"])).toBe(false);
    expect(canEditCatalog(["crm-supervisor"])).toBe(true);
    expect(canEditCatalog(["crm-admin"])).toBe(true);
  });

  it("builds initials from the full name or email", () => {
    expect(userInitials({ full_name: " анна  петрова ", email: "a@x" })).toBe("АП");
    expect(userInitials({ full_name: "", email: "boris@example.test" })).toBe("B");
  });
});
