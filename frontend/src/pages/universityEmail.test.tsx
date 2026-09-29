import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp, sessionFixture } from "../test/utils";

const KAM = () => sessionFixture(["crm-user"], undefined, { id: 5 });

async function openCard(path = "/universities/1") {
  renderApp(path);
  return screen.findByRole("region", { name: /Колледж связи|Технический университет/ });
}

describe("university card: the university's email address", () => {
  it("shows the address at the top of the card as a link that opens the employee's mail program", async () => {
    mockApi({ "GET /auth/me": KAM });
    const card = await openCard();
    const fields = card.querySelector("dl.fields")!;
    expect(fields.querySelector("dt")?.textContent).toBe("Электронная почта вуза");
    const link = within(card).getByRole("link", { name: "priem@ks.example" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("mailto:priem@ks.example");
  });

  it("lets a KAM change it, and shows the new address", async () => {
    let email = "priem@ks.example";
    const api = mockApi({
      "GET /auth/me": KAM,
      "GET /universities": () => [{ ...api.data.universities[0], email }, api.data.universities[1]],
      "PUT /universities/1/email": (call) => {
        email = (call.body as { email: string }).email;
        return { ...api.data.universities[0], email };
      },
    });
    const card = await openCard();
    fireEvent.click(within(card).getByRole("button", { name: "Изменить адрес" }));
    const form = within(card).getByRole("form", { name: "Электронная почта вуза" });
    const input = within(form).getByLabelText("Электронная почта вуза") as HTMLInputElement;
    expect(input.type).toBe("email");
    fireEvent.change(input, { target: { value: "info@ks.example" } });
    fireEvent.submit(form);

    await waitFor(() => expect(api.count("PUT", "/universities/1/email")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ email: "info@ks.example" });
    expect(await within(card).findByRole("link", { name: "info@ks.example" })).toBeTruthy();
    expect(within(card).queryByRole("form", { name: "Электронная почта вуза" })).toBeNull();
  });

  it("offers «Указать адрес» when there is none yet", async () => {
    mockApi({ "GET /auth/me": KAM });
    const card = await openCard("/universities/2");
    expect(within(card).getByText("Не указан")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: "Указать адрес" }));
    expect(within(card).getByRole("form", { name: "Электронная почта вуза" })).toBeTruthy();
  });

  it("keeps the form open with the server's message next to the field", async () => {
    mockApi({
      "GET /auth/me": KAM,
      "PUT /universities/1/email": () =>
        apiError(422, "VALIDATION_ERROR", "Ошибка", [{ field: "email", message: "Некорректный адрес электронной почты" }]),
    });
    const card = await openCard();
    fireEvent.click(within(card).getByRole("button", { name: "Изменить адрес" }));
    const form = within(card).getByRole("form", { name: "Электронная почта вуза" });
    fireEvent.change(within(form).getByLabelText("Электронная почта вуза"), { target: { value: "x@y" } });
    fireEvent.submit(form);
    expect(await within(form).findByText("Некорректный адрес электронной почты")).toBeTruthy();
  });

  it("closes the form on «Отмена» without saving", async () => {
    const api = mockApi({ "GET /auth/me": KAM });
    const card = await openCard();
    fireEvent.click(within(card).getByRole("button", { name: "Изменить адрес" }));
    fireEvent.click(within(card).getByRole("button", { name: "Отмена" }));
    expect(within(card).queryByRole("form", { name: "Электронная почта вуза" })).toBeNull();
    expect(api.count("PUT", "/universities/1/email")).toBe(0);
  });
});
