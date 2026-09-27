import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

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

  it("shows only the placeholder text to a regular user", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/organization");
    await screen.findByText("Реквизиты и контактные данные организации.");
    expect(screen.queryByText("Заявки на адреса отправителей")).toBeNull();
    expect(api.callsTo("GET", "/email-senders/queue")).toHaveLength(0);
  });
});
