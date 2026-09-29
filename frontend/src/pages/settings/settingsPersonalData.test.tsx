import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

const POLICIES = [
  ["Политика в области обработки персональных данных", "/api/v1/documents/personal-data-policy"],
  ["Политика информационной безопасности", "/api/v1/documents/information-security-policy"],
] as const;

describe("settings personal data page", () => {
  it("shows the two policies in order, each as a demo with a Word download from the CRM", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/personal-data");
    const sections = await screen.findAllByRole("region", { name: /^Политика/ });
    expect(sections.map((s) => within(s).getByRole("heading", { level: 2 }).textContent)).toEqual(POLICIES.map(([title]) => title));
    sections.forEach((section, index) => {
      const [title, href] = POLICIES[index];
      expect(within(section).getByText("Демонстрационная версия документа")).toBeTruthy();
      const link = within(section).getByRole("link", { name: `Скачать документ (.docx): ${title}` });
      expect(link.textContent).toContain("Скачать документ (.docx)");
      expect(link.getAttribute("href")).toBe(href);
      expect(link.hasAttribute("download")).toBe(true);
    });
  });

  it("never links to Google Docs and drops the old placeholder", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    const { container } = renderApp("/settings/personal-data");
    await screen.findAllByRole("region", { name: /^Политика/ });
    expect(container.innerHTML).not.toMatch(/docs\.google\.com|drive\.google\.com/);
    expect(screen.queryByText(/Здесь будет представлена/)).toBeNull();
  });
});
