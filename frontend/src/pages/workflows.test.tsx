import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp, sessionFixture } from "../test/utils";

describe("workflows: access", () => {
  it("hides the sidebar item and shows a forbidden state to a crm-user, without calling the API", async () => {
    const api = mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/workflows");
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Процессы" })).toBeNull();
    expect(api.count("GET", "/workflows")).toBe(0);
  });

  it("shows the sidebar item and the editor to supervisors and admins", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-admin"]) });
    renderApp("/workflows");
    const link = await screen.findByRole("link", { name: "Процессы" });
    expect(link.getAttribute("href")).toBe("/workflows");
    expect(await screen.findByText("Типовое взаимодействие с вузом")).toBeTruthy();
    expect(screen.getByText("Короткий процесс")).toBeTruthy();
  });
});

describe("workflows: create", () => {
  it("sends the name, description and one status per line", async () => {
    const api = mockApi({
      "POST /workflows": () => [
        201,
        { id: 3, name: "Новый процесс", description: "", is_default: false, is_active: true, statuses: [] },
      ],
    });
    renderApp("/workflows");
    await screen.findByText("Типовое взаимодействие с вузом");

    fireEvent.change(screen.getByLabelText("Название процесса"), {
      target: { value: "Новый процесс" },
    });
    fireEvent.change(screen.getByLabelText("по одному на строке", { exact: false }), {
      target: { value: "Шаг 1\nШаг 2\nШаг 3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать процесс" }));

    await waitFor(() => expect(api.count("POST", "/workflows")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/workflows")?.body).toEqual({
      name: "Новый процесс",
      description: "",
      statuses: ["Шаг 1", "Шаг 2", "Шаг 3"],
    });
  });

  it("shows a client error and does not call the API when no status is entered", async () => {
    const api = mockApi();
    renderApp("/workflows");
    await screen.findByText("Типовое взаимодействие с вузом");
    fireEvent.change(screen.getByLabelText("Название процесса"), {
      target: { value: "Пустой процесс" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать процесс" }));
    expect(await screen.findByText("Добавьте хотя бы один статус")).toBeTruthy();
    expect(api.count("POST", "/workflows")).toBe(0);
  });
});

describe("workflows: reorder", () => {
  it("moves a status down and sends the full new order", async () => {
    const api = mockApi({
      "PUT /workflows/1/status-order": () => [
        200,
        { id: 1, name: "Типовое взаимодействие с вузом", description: "", is_default: true, is_active: true, statuses: [] },
      ],
    });
    renderApp("/workflows");
    await screen.findByText("Первый контакт");

    fireEvent.click(screen.getByRole("button", { name: "Опустить статус «Первый контакт»" }));

    await waitFor(() => expect(api.count("PUT", "/workflows/1/status-order")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      status_ids: [12, 11, 13, 14],
    });
  });
});

describe("workflows: status deactivation", () => {
  it("asks for a replacement status when the status is in use, then migrates and disables it", async () => {
    const api = mockApi({
      "PATCH /workflow-statuses/12": (call) => {
        const body = call.body as { is_active?: boolean; confirm?: boolean; replacement_status_id?: number };
        if (!body.confirm) {
          return apiError(409, "CONFLICT", "Статус нельзя отключить без подтверждения: в нём 1 взаимодействий", [
            { field: "confirm", message: "Статус нельзя отключить без подтверждения: в нём 1 взаимодействий" },
          ]);
        }
        return [200, { id: 12, name: "Согласование документов", position: 1, is_final: false, is_active: false }];
      },
    });
    renderApp("/workflows");
    await screen.findByText("Согласование документов");

    fireEvent.click(screen.getByRole("button", { name: "Отключитьстатус «Согласование документов»" }));
    expect(await screen.findByText(/Выберите активный статус, куда их перенести/)).toBeTruthy();
    await waitFor(() => expect(api.count("PATCH", "/workflow-statuses/12")).toBe(1));

    fireEvent.change(screen.getByLabelText("Перенести в статус"), { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить перенос и отключение" }));

    await waitFor(() => expect(api.count("PATCH", "/workflow-statuses/12")).toBe(2));
    expect(api.calls.filter((c) => c.method === "PATCH" && c.path === "/workflow-statuses/12")[1].body).toEqual({
      is_active: false,
      confirm: true,
      replacement_status_id: 14,
    });
    await waitFor(() =>
      expect(screen.queryByText(/Выберите активный статус, куда их перенести/)).toBeNull(),
    );
  });
});

describe("workflows: conflicts", () => {
  it("shows the server 409 message when deactivating a workflow fails", async () => {
    mockApi({
      "PATCH /workflows/2": () =>
        apiError(409, "CONFLICT", "Процесс сейчас используется: изменения не применены"),
    });
    renderApp("/workflows");
    await screen.findByText("Короткий процесс");
    const card = screen.getByText("Короткий процесс").closest(".workflow-card")!;
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: "Отключить процесс" }));

    const alert = await within(card as HTMLElement).findByRole("alert");
    expect(alert.textContent).toBe(
      "Процесс сейчас используется: изменения не применены (код CONFLICT)",
    );
  });
});
