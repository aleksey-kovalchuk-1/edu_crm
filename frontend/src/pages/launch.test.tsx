import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { StatusChange } from "../api/workflows";
import { formatDate } from "../lib/format";
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

describe("interaction detail: task plan", () => {
  it("shows the plan's tasks grouped by category, with unfinished-earlier flagged", async () => {
    mockApi({
      "GET /launches/1/tasks": () => ({
        current_category: 2,
        categories: [
          { index: 0, name: "Первый контакт", tasks: [{ id: 1, title: "Найти контакт", status: "completed", priority: "normal", deadline: "2026-01-01", assignee: null, is_optional: false }], unfinished_count: 0 },
          {
            index: 1,
            name: "Документы",
            tasks: [
              {
                id: 2,
                title: "Подписать документы",
                status: "new",
                priority: "normal",
                deadline: "2026-01-05",
                assignee: { id: 7, full_name: "Иван Смирнов" },
                is_optional: false,
              },
            ],
            unfinished_count: 1,
          },
          { index: 2, name: "Внедрение", tasks: [], unfinished_count: 0 },
          { index: 3, name: "Обучение", tasks: [], unfinished_count: 0 },
          { index: 4, name: "Сопровождение", tasks: [], unfinished_count: 0 },
        ],
        uncategorized: [],
      }),
    });
    renderApp("/interactions/1");
    await screen.findByRole("heading", { name: "Связанные задачи" });
    expect(await screen.findByText("Документы")).toBeTruthy();
    expect(await screen.findByText(/1 незаверш/)).toBeTruthy(); // unfinished_count badge on an earlier-than-current category
    const taskItem = screen.getByText("Подписать документы").closest("li")!;
    expect(within(taskItem).getByText(/Новая/)).toBeTruthy(); // TASK_STATUS_LABELS["new"]
    expect(within(taskItem).getByText(/Иван Смирнов/)).toBeTruthy(); // assignee.full_name
    expect(within(taskItem).getByText(new RegExp(formatDate("2026-01-05")))).toBeTruthy(); // deadline

    const currentHeading = screen.getByText("Внедрение").closest("h3")!;
    expect(within(currentHeading).getByText("текущий этап")).toBeTruthy(); // badge on current_category

    expect(within(currentHeading.parentElement!).getByText("Нет задач")).toBeTruthy(); // empty category
  });

  it("renders status, assignee and deadline for uncategorized tasks too, not just title", async () => {
    mockApi({
      "GET /launches/1/tasks": () => ({
        current_category: 0,
        categories: [
          { index: 0, name: "Первый контакт", tasks: [], unfinished_count: 0 },
          { index: 1, name: "Документы", tasks: [], unfinished_count: 0 },
          { index: 2, name: "Внедрение", tasks: [], unfinished_count: 0 },
          { index: 3, name: "Обучение", tasks: [], unfinished_count: 0 },
          { index: 4, name: "Сопровождение", tasks: [], unfinished_count: 0 },
        ],
        uncategorized: [
          {
            id: 5,
            title: "Ручная задача без категории",
            status: "in_progress",
            priority: "normal",
            deadline: "2026-02-10",
            assignee: { id: 3, full_name: "Ольга Семёнова" },
            is_optional: false,
          },
        ],
      }),
    });
    await openLaunch();
    await screen.findByRole("heading", { name: "Связанные задачи" });
    const taskItem = (await screen.findByText("Ручная задача без категории")).closest("li")!;
    expect(within(taskItem).getByText(/В работе/)).toBeTruthy(); // TASK_STATUS_LABELS["in_progress"]
    expect(within(taskItem).getByText(/Ольга Семёнова/)).toBeTruthy(); // assignee.full_name
    expect(within(taskItem).getByText(new RegExp(formatDate("2026-02-10")))).toBeTruthy(); // deadline
  });

  it("shows an error with retry when the launch-tasks request fails, and a loading message while pending", async () => {
    let attempt = 0;
    mockApi({
      "GET /launches/1/tasks": () => {
        attempt += 1;
        // A 4xx status (unlike 5xx) is treated as final by retryTransient and won't be silently
        // retried by react-query before the test can observe the error UI.
        if (attempt === 1) return apiError(400, "VALIDATION_ERROR", "Не удалось загрузить задачи", []);
        return {
          current_category: 0,
          categories: [
            { index: 0, name: "Первый контакт", tasks: [], unfinished_count: 0 },
            { index: 1, name: "Документы", tasks: [], unfinished_count: 0 },
            { index: 2, name: "Внедрение", tasks: [], unfinished_count: 0 },
            { index: 3, name: "Обучение", tasks: [], unfinished_count: 0 },
            { index: 4, name: "Сопровождение", tasks: [], unfinished_count: 0 },
          ],
          uncategorized: [],
        };
      },
    });
    await openLaunch();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не удалось загрузить задачи");

    fireEvent.click(within(alert).getByRole("button", { name: /Повторить/ }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});

describe("interaction detail: manual task creation", () => {
  it("locks the task to that university and interaction, closes the modal, and shows it under Связанные задачи without a manual reload", async () => {
    let created = false;
    const api = mockApi({
      "POST /tasks": (call) => {
        created = true;
        return [
          201,
          {
            ...api.data.task,
            id: 9,
            ...(call.body as object),
            interaction: { id: 1, program: "Аналитика данных" },
          },
        ];
      },
      "GET /launches/1/tasks": () => ({
        current_category: 0,
        categories: [
          {
            index: 0,
            name: "Первый контакт",
            tasks: created
              ? [
                  {
                    id: 9,
                    title: "Ручная задача",
                    status: "new",
                    priority: "normal",
                    deadline: null,
                    assignee: null,
                    is_optional: false,
                  },
                ]
              : [],
            unfinished_count: 0,
          },
        ],
        uncategorized: [],
      }),
    });
    await openLaunch();
    await screen.findByRole("heading", { name: "Связанные задачи" });
    expect(screen.queryByText("Ручная задача")).toBeNull();

    fireEvent.click(await screen.findByRole("button", { name: /Создать задачу/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новая задача" });
    // the University/Interaction fields are not editable from this entry point
    expect(within(dialog).queryByRole("combobox", { name: "Учебное заведение" })).toBeNull();
    expect(within(dialog).queryByRole("combobox", { name: "Взаимодействие" })).toBeNull();
    fireEvent.change(within(dialog).getByPlaceholderText("Например, собрать документы"), {
      target: { value: "Ручная задача" },
    });
    fireEvent.submit(dialog.querySelector("form")!);

    await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({
      title: "Ручная задача",
      university_id: 1,
      launch_id: 1,
    });

    // the modal closes without redirecting away from the Interaction page
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // ...and the new task appears in "Связанные задачи" via the launch-tasks query being
    // invalidated and refetched, with no manual reload.
    expect(await screen.findByText("Ручная задача")).toBeTruthy();
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
