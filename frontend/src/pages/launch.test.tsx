import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { StatusChange } from "../api/workflows";
import { CSRF_TOKEN, apiError, mockApi, renderApp } from "../test/utils";

const CHANGES: StatusChange[] = [
  {
    id: 2,
    launch_id: 1,
    from_status: { id: 11, name: "Первый контакт" },
    to_status: { id: 12, name: "Согласование документов" },
    comment: "Документы переданы на подпись",
    author: { id: 5, full_name: "Ирина Петрова" },
    created_at: "2026-09-10T09:00:00Z",
    attachments: [
      { id: 9, filename: "договор.pdf", content_type: "application/pdf", size_bytes: 20480, created_at: "2026-09-10T09:00:00Z" },
    ],
  },
  {
    id: 1,
    launch_id: 1,
    from_status: null,
    to_status: { id: 11, name: "Первый контакт" },
    comment: "",
    author: null,
    created_at: "2026-09-01T09:00:00Z",
    attachments: [],
  },
];

async function openLaunch() {
  renderApp("/interactions/1");
  return screen.findByRole("heading", { level: 2, name: "Аналитика данных" });
}

describe("interaction detail: timeline", () => {
  it("renders status changes newest first with comments, authors and attachment links", async () => {
    mockApi({ "GET /launches/1/status-changes": () => CHANGES });
    await openLaunch();
    const items = await screen.findAllByRole("listitem");
    const timelineItems = items.filter((el) => el.className.includes("timeline-item"));
    expect(timelineItems).toHaveLength(2);
    // Newest first: the second change (id 2) renders before the creation record (id 1).
    expect(timelineItems[0].textContent).toContain("Первый контакт");
    expect(timelineItems[0].textContent).toContain("Согласование документов");
    expect(timelineItems[0].textContent).toContain("Ирина Петрова");
    expect(timelineItems[0].textContent).toContain("Документы переданы на подпись");
    expect(timelineItems[1].textContent).toContain("Создано в статусе «Первый контакт»");
    expect(timelineItems[1].textContent).toContain("Системная запись");

    const link = screen.getByRole("link", { name: /договор\.pdf/ }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/api/v1/attachments/9");
  });

  it("shows an empty message when there is no history yet", async () => {
    mockApi({ "GET /launches/1/status-changes": () => [] });
    await openLaunch();
    expect(await screen.findByText("История пока пуста.")).toBeTruthy();
  });
});

describe("interaction detail: status change dialog", () => {
  async function openDialog() {
    await openLaunch();
    fireEvent.click(screen.getByRole("button", { name: "Сменить статус" }));
    return screen.findByRole("dialog", { name: "Сменить статус" });
  }

  it("sends status_id, comment and files as multipart form data with the CSRF header", async () => {
    const api = mockApi({
      "POST /launches/1/status-changes": () => [
        201,
        {
          id: 3,
          launch_id: 1,
          from_status: { id: 12, name: "Согласование документов" },
          to_status: { id: 14, name: "Сопровождение" },
          comment: "Готово",
          author: { id: 1, full_name: "Анна Петрова" },
          created_at: "2026-09-15T10:00:00Z",
          attachments: [],
        },
      ],
    });
    const dialog = await openDialog();

    fireEvent.change(within(dialog).getByLabelText("Статус"), { target: { value: "14" } });
    fireEvent.change(within(dialog).getByLabelText("Комментарий", { exact: false }), {
      target: { value: "Готово" },
    });
    const file = new File(["contents"], "report.pdf", { type: "application/pdf" });
    fireEvent.change(within(dialog).getByLabelText("Прикрепить файлы"), {
      target: { files: [file] },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(api.count("POST", "/launches/1/status-changes")).toBe(1));
    const call = api.calls.find((c) => c.method === "POST" && c.path === "/launches/1/status-changes")!;
    expect(call.headers["x-csrf-token"]).toBe(CSRF_TOKEN);
    const body = call.body as FormData;
    expect(body.get("status_id")).toBe("14");
    expect(body.get("comment")).toBe("Готово");
    const files = body.getAll("files") as File[];
    expect(files).toHaveLength(1);
    expect(files[0].name).toBe("report.pdf");

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("rejects an unsupported file client-side without calling the API", async () => {
    const api = mockApi();
    const dialog = await openDialog();

    const file = new File(["x"], "virus.exe");
    fireEvent.change(within(dialog).getByLabelText("Прикрепить файлы"), {
      target: { files: [file] },
    });

    expect(
      await within(dialog).findByText(/Файл «virus\.exe» не подходит/),
    ).toBeTruthy();
    expect(within(dialog).queryByText("virus.exe")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(api.count("POST", "/launches/1/status-changes")).toBe(0);
  });

  it("shows a server 422 field error next to the comment field", async () => {
    mockApi({
      "POST /launches/1/status-changes": () =>
        apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
          { field: "comment", message: "Комментарий длиннее 2000 символов" },
        ]),
    });
    const dialog = await openDialog();
    fireEvent.change(within(dialog).getByLabelText("Статус"), { target: { value: "14" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    expect(await within(dialog).findByText("Комментарий длиннее 2000 символов")).toBeTruthy();
    expect(within(dialog).getByRole("alert").textContent).toBe(
      "Проверьте заполненные поля (код VALIDATION_ERROR)",
    );
  });

  it("shows a server 415 unsupported-media error for files", async () => {
    mockApi({
      "POST /launches/1/status-changes": () =>
        apiError(415, "UNSUPPORTED_MEDIA_TYPE", "Неподдерживаемый формат данных", [
          { field: "files", message: "Файл «отчёт.png»: содержимое не соответствует расширению .png" },
        ]),
    });
    const dialog = await openDialog();
    fireEvent.change(within(dialog).getByLabelText("Статус"), { target: { value: "14" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    expect(
      await within(dialog).findByText("Файл «отчёт.png»: содержимое не соответствует расширению .png"),
    ).toBeTruthy();
    expect(within(dialog).getByRole("alert").textContent).toContain("UNSUPPORTED_MEDIA_TYPE");
  });
});
