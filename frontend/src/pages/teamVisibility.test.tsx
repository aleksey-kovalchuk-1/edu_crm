import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

describe("university card: «Видят все КАМ»", () => {
  it("lets a head share a university with every KAM", async () => {
    let shared = false;
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-supervisor"]),
      "GET /universities": () => [{ ...api.data.universities[0], team_visible_to_managers: shared }, api.data.universities[1]],
      "PATCH /universities/1": (call) => {
        shared = (call.body as { team_visible_to_managers: boolean }).team_visible_to_managers;
        return { ...api.data.universities[0], team_visible_to_managers: shared };
      },
    });
    renderApp("/universities/1");
    const card = await screen.findByRole("region", { name: /Колледж связи/ });
    const toggle = within(card).getByRole("checkbox", { name: "Видят все КАМ" }) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect(within(card).getByText(/только назначенные КАМ/)).toBeTruthy();
    fireEvent.click(toggle);
    await waitFor(() => expect(api.callsTo("PATCH", "/universities/1")).toHaveLength(1));
    expect(api.callsTo("PATCH", "/universities/1")[0].body).toEqual({ team_visible_to_managers: true });
    await waitFor(() => expect((within(card).getByRole("checkbox", { name: "Видят все КАМ" }) as HTMLInputElement).checked).toBe(true));
  });

  it("shows a KAM who can see the university, without the switch", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"], undefined, { id: 5 }) });
    renderApp("/universities/2");
    const card = await screen.findByRole("region", { name: /Технический университет/ });
    expect(within(card).queryByRole("checkbox", { name: "Видят все КАМ" })).toBeNull();
    expect(within(card).getByText("Все КАМ")).toBeTruthy();
  });
});
