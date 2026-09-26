import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

describe("university settings", () => {
  it("lets a manager add a university and immediately create its first task", async () => {
    const api = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"]),
      "POST /universities": () => [201, {
        ...api.data.universities[0], id: 23, name: "Новый вуз", city: "Казань",
        managers: [{ id: 1, full_name: "Анна Петрова" }],
      }],
      "POST /tasks": () => [201, {
        ...api.data.task, id: 99, title: "Первый звонок",
        university: { id: 23, name: "Новый вуз" },
      }],
    });
    renderApp("/settings/universities");

    fireEvent.click(await screen.findByRole("button", { name: "Добавить вуз" }));
    const universityDialog = await screen.findByRole("dialog", { name: "Новое учебное заведение" });
    fireEvent.change(within(universityDialog).getByLabelText("Название"), { target: { value: "Новый вуз" } });
    fireEvent.change(within(universityDialog).getByLabelText("Город"), { target: { value: "Казань" } });
    fireEvent.submit(universityDialog.querySelector("form")!);
    await waitFor(() => expect(api.count("POST", "/universities")).toBe(1));
    expect(api.calls.find((call) => call.method === "POST" && call.path === "/universities")?.body)
      .toMatchObject({ name: "Новый вуз", city: "Казань" });

    fireEvent.click(await screen.findByRole("button", { name: "Создать задачу по вузу" }));
    const taskDialog = await screen.findByRole("dialog", { name: "Новая задача" });
    expect(within(taskDialog).getByText("Новый вуз")).toBeTruthy();
    fireEvent.change(within(taskDialog).getByLabelText("Название"), { target: { value: "Первый звонок" } });
    fireEvent.submit(taskDialog.querySelector("form")!);
    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((call) => call.method === "POST" && call.path === "/tasks")?.body)
      .toMatchObject({ title: "Первый звонок", university_id: 23 });
  });
});
