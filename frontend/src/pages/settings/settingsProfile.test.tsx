import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, profileFixture, renderApp } from "../../test/utils";

const PHONE_STEP_TITLE = "Мобильный телефон";

function openPhoneStep() {
  fireEvent.click(screen.getByRole("button", { name: "Добавить номер" }));
}

describe("settings profile — personal data", () => {
  it("saves names, time zone and contacts in one PATCH without the phone", async () => {
    const api = mockApi({
      "PATCH /profile": (call) => profileFixture({ ...(call.body as object), full_name: "Анна Смирнова" }),
    });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Фамилия"), { target: { value: "Смирнова" } });
    fireEvent.change(screen.getByLabelText("Отчество"), { target: { value: "Сергеевна" } });
    fireEvent.change(screen.getByLabelText("Telegram"), { target: { value: "@anna_demo" } });
    fireEvent.change(screen.getByLabelText("WhatsApp"), { target: { value: "+79991234567" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("Изменения сохранены");
    expect(api.callsTo("PATCH", "/profile")[0].body).toEqual({
      first_name: "Анна", middle_name: "Сергеевна", last_name: "Смирнова", timezone: "Europe/Moscow",
      telegram: "@anna_demo", whatsapp: "+79991234567",
    });
  });

  it("keeps the form filled and shows the server error when Keycloak is down", async () => {
    mockApi({
      "PATCH /profile": () =>
        apiError(503, "SERVICE_UNAVAILABLE", "Не удалось сохранить имя: сервис учётных записей недоступен, попробуйте позже"),
    });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Фамилия"), { target: { value: "Смирнова" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText(/сервис учётных записей недоступен/);
    expect((screen.getByLabelText("Фамилия") as HTMLInputElement).value).toBe("Смирнова");
    expect(screen.queryByText("Изменения сохранены")).toBeNull();
  });

  it("shows field errors next to the field", async () => {
    mockApi({
      "PATCH /profile": () =>
        apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
          { field: "telegram", message: "Имя пользователя Telegram: 5–32 символа", type: "value_error" },
        ]),
    });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Telegram"), { target: { value: "ab" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("Имя пользователя Telegram: 5–32 символа");
  });

  it("shows a contact as saved only after it is saved, then shows the server-normalized value", async () => {
    mockApi({ "PATCH /profile": () => profileFixture({ telegram: "anna_demo" }) });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Telegram"), { target: { value: "@anna_demo" } });
    expect(screen.queryByText("Сохранён · не подключён")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("Сохранён · не подключён");
    expect((screen.getByLabelText("Telegram") as HTMLInputElement).value).toBe("anna_demo");
  });

  it("labels saved contacts honestly: saved, not connected", async () => {
    mockApi({ "GET /profile": () => profileFixture({ telegram: "anna_demo" }) });
    renderApp("/settings/profile");
    await screen.findByText("Сохранён · не подключён");
    screen.getByText("Не указан");
    screen.getByText(/не отправляет сообщения в мессенджеры/);
  });
});

describe("settings profile — mobile phone verification", () => {
  it("requests a code for a mobile number", async () => {
    const api = mockApi({ "POST /profile/phone": () => ({ expires_in: 300 }) });
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);
    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), { target: { value: "+7 999 123-45-67" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByLabelText(/Код из SMS/);
    expect(api.callsTo("POST", "/profile/phone")[0].body).toEqual({ phone: "+7 999 123-45-67" });
  });

  it("rejects a landline locally, without calling the server", async () => {
    const api = mockApi();
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);
    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), { target: { value: "+7 495 123-45-67" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    screen.getByText("Введите мобильный номер в формате +7 9XX XXX-XX-XX");
    expect(screen.queryByLabelText(/Код из SMS/)).toBeNull();
    expect(api.callsTo("POST", "/profile/phone")).toHaveLength(0);
  });

  it("never shows an entered number as verified before the code is confirmed", async () => {
    mockApi({ "POST /profile/phone": () => ({ expires_in: 300 }) });
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);
    screen.getByText("Номер не подтверждён");
    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), { target: { value: "+79991234567" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByText(/Ожидает подтверждения/);
    expect(screen.queryByText(/Подтверждён/)).toBeNull();
  });

  it("confirms a code and shows the verified state without a page reload", async () => {
    const api = mockApi({
      "POST /profile/phone": () => ({ expires_in: 300 }),
      "POST /profile/phone/verify": () => ({ phone: "+79991234567", phone_verified_at: "2026-09-16T12:00:00Z" }),
    });
    renderApp("/settings/profile");
    await screen.findByText(PHONE_STEP_TITLE);
    openPhoneStep();
    fireEvent.change(screen.getByLabelText("Номер телефона"), { target: { value: "+79991234567" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByLabelText(/Код из SMS/);
    fireEvent.change(screen.getByLabelText(/Код из SMS/), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await screen.findByText(/Подтверждён:/);
    screen.getByText("+79991234567");
    expect(api.callsTo("POST", "/profile/phone/verify")[0].body).toEqual({ code: "123456" });
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
    fireEvent.change(screen.getByLabelText("Номер телефона"), { target: { value: "+79991234567" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByLabelText(/Код из SMS/);
    fireEvent.change(screen.getByLabelText(/Код из SMS/), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await screen.findByText(/Неверный код, попробуйте ещё раз/);
    screen.getByLabelText(/Код из SMS/);
  });
});

describe("settings profile — sender address", () => {
  it("marks a stored selection that is no longer usable", async () => {
    mockApi({
      "GET /profile": () => profileFixture({ email_sender_identity_id: 7 }),
      "GET /email-senders": () => [{ id: 7, email_address: "old@uni-demo.ru", display_name: "Старый", is_active: false,
        status: "active", is_shared: true, rejection_reason: "", usable: false }],
    });
    renderApp("/settings/profile");
    await screen.findByText(/old@uni-demo.ru — недоступен/);
  });

  it("submits a personal sender request", async () => {
    const api = mockApi({
      "POST /email-senders/requests": () => ({ id: 3, email_address: "anna@uni-demo.ru", display_name: "Анна",
        is_active: true, status: "pending_approval", is_shared: false, rejection_reason: "", usable: false }),
    });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Новый адрес"), { target: { value: "anna@uni-demo.ru" } });
    fireEvent.change(screen.getByLabelText("Имя отправителя"), { target: { value: "Анна" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить на одобрение" }));
    await waitFor(() => expect(api.callsTo("POST", "/email-senders/requests")).toHaveLength(1));
    expect(api.callsTo("POST", "/email-senders/requests")[0].body).toEqual({ email_address: "anna@uni-demo.ru", display_name: "Анна" });
  });

  it("shows own request status and rejection reason", async () => {
    mockApi({
      "GET /email-senders": () => [{ id: 4, email_address: "anna@uni-demo.ru", display_name: "Анна", is_active: true,
        status: "rejected", is_shared: false, rejection_reason: "Чужой домен", usable: false }],
    });
    renderApp("/settings/profile");
    await screen.findByText(/Отклонён/);
    screen.getByText(/Чужой домен/);
  });

  it("labels a deactivated own address as deactivated and still allows a new request", async () => {
    mockApi({
      "GET /email-senders": () => [
        { id: 4, email_address: "old@uni-demo.ru", display_name: "Анна", is_active: false,
          status: "active", is_shared: false, rejection_reason: "", usable: false },
        { id: 5, email_address: "stale@uni-demo.ru", display_name: "Анна", is_active: false,
          status: "pending_approval", is_shared: false, rejection_reason: "", usable: false },
      ],
    });
    renderApp("/settings/profile");
    await screen.findByText(/old@uni-demo.ru/);
    expect(screen.getAllByText(/Деактивирован/)).toHaveLength(2);
    expect(screen.queryByText(/Подтверждён/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Отозвать заявку" })).toBeNull();
    screen.getByLabelText("Новый адрес");
  });
});
