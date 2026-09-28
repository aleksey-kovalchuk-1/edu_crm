import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, organizationFixture, renderApp, sessionFixture } from "../../test/utils";

const pending = {
  id: 5, email_address: "anna@uni-demo.ru", display_name: "Анна", is_active: true, status: "pending_approval",
  is_shared: false, rejection_reason: "", usable: false, requested_by: "Анна Петрова", requested_at: "2026-09-27T10:00:00Z",
};

describe("organization sender queue", () => {
  it("lets a supervisor approve and shows the delivery message", async () => {
    const api = mockApi({
      "GET /email-senders/queue": () => [pending],
      "POST /email-senders/5/approve": () => ({
        delivered: false, message: "Почтовый провайдер не настроен: письмо подтверждения записано только в журнал сервера.",
      }),
    });
    renderApp("/settings/organization");
    fireEvent.click(await screen.findByRole("button", { name: "Одобрить anna@uni-demo.ru" }));
    await screen.findByText(/записано только в журнал сервера/);
    expect(api.callsTo("POST", "/email-senders/5/approve")).toHaveLength(1);
  });

  it("rejects with a reason", async () => {
    const api = mockApi({ "GET /email-senders/queue": () => [pending], "POST /email-senders/5/reject": () => [204, null] });
    renderApp("/settings/organization");
    fireEvent.click(await screen.findByRole("button", { name: "Отклонить anna@uni-demo.ru" }));
    fireEvent.change(screen.getByLabelText("Причина отказа"), { target: { value: "Чужой домен" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить отказ" }));
    await waitFor(() => expect(api.callsTo("POST", "/email-senders/5/reject")).toHaveLength(1));
    expect(api.callsTo("POST", "/email-senders/5/reject")[0].body).toEqual({ reason: "Чужой домен" });
  });

  it("adds a shared address", async () => {
    const api = mockApi({
      "POST /email-senders": () => [201, { id: 9, email_address: "office@uni-demo.ru", display_name: "Офис", is_active: true,
        status: "awaiting_confirmation", is_shared: true, rejection_reason: "", usable: false }],
    });
    renderApp("/settings/organization");
    fireEvent.change(await screen.findByLabelText("Адрес"), { target: { value: "office@uni-demo.ru" } });
    fireEvent.change(screen.getByLabelText("Имя отправителя"), { target: { value: "Офис" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить общий адрес" }));
    await screen.findByText(/отправлено письмо подтверждения/);
    expect(api.callsTo("POST", "/email-senders")[0].body).toEqual({ email_address: "office@uni-demo.ru", display_name: "Офис" });
  });

  it("shows the organization card read-only to a regular user, without the queue", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/organization");
    await screen.findByText("ИТ Школа Ростелеком");
    screen.getByText("1095030001131");
    screen.getByText("+7 (495) 196-62-05");
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    expect(screen.queryByLabelText("Название")).toBeNull();
    expect(screen.queryByText("Заявки на адреса отправителей")).toBeNull();
    expect(api.callsTo("GET", "/email-senders/queue")).toHaveLength(0);
  });
});

describe("organization card editing", () => {
  it("lets an admin save all fields in one PUT and confirms success", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-admin"]),
      "PUT /organization": (call) => organizationFixture(call.body as Record<string, unknown>),
    });
    renderApp("/settings/organization");
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "ИТ Школа" } });
    fireEvent.change(screen.getByLabelText("Телефон"), { target: { value: "8 495 196-62-05" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("Изменения сохранены");
    expect(api.callsTo("PUT", "/organization")[0].body).toEqual({
      name: "ИТ Школа",
      legal_name: "Общество с ограниченной ответственностью «Ростелеком Информационные Технологии»",
      ogrn: "1095030001131", registration_date: "2009-04-10",
      legal_address: "108811, г. Москва, Киевское шоссе, 22-й км, домовладение 6, стр. 1, офис Е434",
      postal_address: "108811, г. Москва, Киевское шоссе, 22-й км, домовладение 6, стр. 1, офис Е434",
      contact_address: "Москва, проспект Вернадского, д. 41", phone: "8 495 196-62-05", email: "edupro@rt.ru",
    });
  });

  it("shows a field error next to the field", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-admin"]),
      "PUT /organization": () => apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
        { field: "ogrn", message: "ОГРН — 13 цифр с верной контрольной цифрой", type: "value_error" },
      ]),
    });
    renderApp("/settings/organization");
    fireEvent.change(await screen.findByLabelText("ОГРН"), { target: { value: "1095030001132" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("ОГРН — 13 цифр с верной контрольной цифрой");
    expect(screen.queryByText("Изменения сохранены")).toBeNull();
  });

  it("summarises field errors above the form and moves focus to the field from the summary", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-admin"]),
      "PUT /organization": () => apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
        { field: "ogrn", message: "ОГРН — 13 цифр с верной контрольной цифрой", type: "value_error" },
      ]),
    });
    renderApp("/settings/organization");
    fireEvent.change(await screen.findByLabelText("ОГРН"), { target: { value: "1095030001132" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    const summary = await screen.findByRole("group", { name: /Исправьте 1 поле/ });
    expect(document.activeElement).toBe(summary);
    fireEvent.click(screen.getByRole("link", { name: /ОГРН: ОГРН — 13 цифр/ }));
    expect(document.activeElement?.id).toBe("organization-ogrn");
  });
});
