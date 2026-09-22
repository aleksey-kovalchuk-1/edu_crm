import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp } from "../../test/utils";

const PHONE_STEP_TITLE = "Телефон";

function openPhoneStep() {
  fireEvent.click(screen.getByRole("button", { name: "Добавить номер" }));
}

describe("settings profile phone verification", () => {
  it("requests a code for a validly formatted phone number", async () => {
    const api = mockApi({
      "POST /profile/phone": () => ({ expires_in: 300 }),
    });
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);

    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), {
      target: { value: "+7 999 123-45-67" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));

    await screen.findByLabelText(/Код из SMS/);
    screen.getByText(/Код отправлен на номер/);
    const call = api.calls.find((c) => c.method === "POST" && c.path === "/profile/phone");
    expect(call?.body).toEqual({ phone: "+7 999 123-45-67" });
  });

  it("rejects an implausible phone number locally, without calling the server", async () => {
    const api = mockApi();
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);

    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), {
      target: { value: "not a phone" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));

    screen.getByText("Введите номер телефона в формате +7XXXXXXXXXX, 8XXXXXXXXXX или 7XXXXXXXXXX");
    // Still on the phone step: the code field never appeared.
    expect(screen.queryByLabelText(/Код из SMS/)).toBeNull();
    expect(api.callsTo("POST", "/profile/phone")).toHaveLength(0);
  });

  it("confirms a code and shows the verified state without a page reload", async () => {
    const api = mockApi({
      "POST /profile/phone": () => ({ expires_in: 300 }),
      "POST /profile/phone/verify": () => ({
        phone: "+79991234567",
        phone_verified_at: "2026-09-16T12:00:00Z",
      }),
    });
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);

    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), {
      target: { value: "+79991234567" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByLabelText(/Код из SMS/);

    fireEvent.change(screen.getByLabelText(/Код из SMS/), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

    await screen.findByText(/Подтверждён:/);
    screen.getByText("+79991234567");
    const call = api.calls.find((c) => c.method === "POST" && c.path === "/profile/phone/verify");
    expect(call?.body).toEqual({ code: "123456" });
  });

  it("shows the server's error message when the code is rejected", async () => {
    mockApi({
      "POST /profile/phone": () => ({ expires_in: 300 }),
      "POST /profile/phone/verify": () =>
        apiError(422, "VALIDATION_ERROR", "Неверный код, попробуйте ещё раз", [
          { field: "code", message: "Неверный код, попробуйте ещё раз", type: "value_error" },
        ]),
    });
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);

    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), {
      target: { value: "+79991234567" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByLabelText(/Код из SMS/);

    fireEvent.change(screen.getByLabelText(/Код из SMS/), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

    await screen.findByText(/Неверный код, попробуйте ещё раз/);
    // Still on the code step: a wrong code does not throw the user back to the view step.
    screen.getByLabelText(/Код из SMS/);
  });
});
