import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { ImportReport, ImportUpload } from "../api/imports";
import {
  CSRF_TOKEN,
  apiError,
  mockApi,
  renderApp,
  sessionFixture,
  type Call,
} from "../test/utils";

const FIELDS = [
  { name: "university_name", label: "Наименование вуза", required: true },
  { name: "vendor", label: "Вендор", required: true },
  { name: "software", label: "ПО", required: true },
  { name: "contract_number", label: "Номер договора", required: true },
  { name: "license_signed_at", label: "Подписание лицензии", required: true },
  { name: "license_valid_until", label: "Срок действия лицензии", required: false },
  { name: "comment", label: "Комментарий", required: false },
];

const UPLOAD: ImportUpload = {
  id: 4,
  filename: "реестр.xlsx",
  status: "uploaded",
  header_row: 2,
  headers: ["Наименование вуза", "Вендор", "ИТ-продукт", "№ договора", "Дата подписания", "Примечание"],
  mapping: {
    university_name: "Наименование вуза",
    vendor: "Вендор",
    software: "ИТ-продукт",
    contract_number: "№ договора",
    license_signed_at: "Дата подписания",
    license_valid_until: null,
    comment: null,
  },
  row_count: 3,
  preview: [
    {
      row_number: 3,
      cells: ["Волжский институт", "РТК ИТ", "Учебная среда", "Д-001", "2026-01-15", null],
    },
  ],
  created_at: "2026-09-16T02:10:00Z",
  created_by: { id: 2, full_name: "Павел Демо" },
  report: null,
};

const REPORT: ImportReport = {
  summary: {
    rows: 3,
    valid: 2,
    invalid: 1,
    skipped: 0,
    with_warnings: 1,
    created: { universities: 1, contracts: 1 },
    updated: { contracts: 1 },
  },
  rows: [
    { row_number: 3, status: "ok", action: "create", contract_number: "Д-001", errors: [], warnings: [] },
    {
      row_number: 4,
      status: "warning",
      action: "update",
      contract_number: "Д-007",
      errors: [],
      warnings: ["Менеджер не найден среди пользователей CRM"],
    },
    {
      row_number: 5,
      status: "error",
      action: null,
      contract_number: "",
      errors: ["Не заполнено поле «Номер договора»"],
      warnings: [],
    },
  ],
};

const importHandlers = (extra: Record<string, (call: Call) => unknown> = {}) => ({
  "GET /imports/fields": () => FIELDS,
  "GET /imports": () => [],
  "POST /imports": () => [201, UPLOAD],
  "POST /imports/4/check": () => REPORT,
  ...extra,
});

const xlsx = (name = "реестр.xlsx", size?: number) => {
  const file = new File(["data"], name);
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
};

const chooseFile = async (file: File) => {
  const input = await screen.findByLabelText("Выберите файл");
  fireEvent.change(input, { target: { files: [file] } });
};

const currentStep = () =>
  screen
    .getByRole("navigation", { name: "Шаги загрузки" })
    .querySelector('[aria-current="step"]')?.textContent;

/** Uploads a valid file and waits for the mapping step. */
async function uploadFile() {
  await chooseFile(xlsx());
  fireEvent.click(screen.getByRole("button", { name: /Загрузить файл/ }));
  return (await screen.findByLabelText("Наименование вуза")) as HTMLSelectElement;
}

async function checkMapping() {
  await uploadFile();
  fireEvent.click(screen.getByRole("button", { name: "Проверить" }));
}

describe("imports: access", () => {
  it("hides the sidebar item and shows a forbidden state to a crm-user", async () => {
    const api = mockApi({ ...importHandlers(), "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/imports");
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Загрузка справочников/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Справочники/ })).toBeTruthy();
    expect(api.count("GET", "/imports/fields")).toBe(0);
    expect(api.count("GET", "/imports")).toBe(0);
  });

  it("shows the sidebar item to supervisors and admins", async () => {
    mockApi({ ...importHandlers(), "GET /auth/me": () => sessionFixture(["crm-admin"]) });
    renderApp("/imports");
    const link = await screen.findByRole("link", { name: /Загрузка справочников/ });
    expect(link.getAttribute("href")).toBe("/imports");
    expect(currentStep()).toContain("Файл");
    expect(await screen.findByText("Загрузок пока не было.")).toBeTruthy();
  });
});

describe("imports: file step", () => {
  it("rejects a wrong extension and an oversize file without calling the API", async () => {
    const api = mockApi(importHandlers());
    renderApp("/imports");
    await chooseFile(xlsx("реестр.csv"));
    expect((await screen.findByRole("alert")).textContent).toContain("в формате .xls или .xlsx");
    const upload = screen.getByRole("button", { name: /Загрузить файл/ }) as HTMLButtonElement;
    expect(upload.disabled).toBe(true);

    await chooseFile(xlsx("big.xlsx", 11 * 1024 * 1024));
    expect(screen.getByRole("alert").textContent).toContain("больше допустимых 10 МБ");

    const dropzone = screen.getByText("Перетащите файл сюда или").closest("div") as HTMLElement;
    fireEvent.drop(dropzone, { dataTransfer: { files: [xlsx("scan.pdf")] } });
    expect(screen.getByRole("alert").textContent).toContain("«scan.pdf»");

    fireEvent.submit(upload.closest("form")!);
    expect(api.count("POST", "/imports")).toBe(0);
  });

  it("uploads the file as multipart with the CSRF token and prefills the mapping", async () => {
    const api = mockApi(importHandlers());
    renderApp("/imports");
    const university = await uploadFile();
    const call = api.calls.find((c) => c.method === "POST" && c.path === "/imports")!;
    expect(call.body).toBeInstanceOf(FormData);
    expect(((call.body as FormData).get("file") as File).name).toBe("реестр.xlsx");
    expect(call.headers["content-type"]).toBeUndefined();
    expect(call.headers["x-csrf-token"]).toBe(CSRF_TOKEN);

    expect(university.value).toBe("Наименование вуза");
    expect((screen.getByLabelText("ПО") as HTMLSelectElement).value).toBe("ИТ-продукт");
    expect((screen.getByLabelText("Комментарий") as HTMLSelectElement).value).toBe("");
    expect(currentStep()).toContain("Сопоставление");
    const preview = screen.getByRole("region", { name: "Первые строки файла" });
    expect(within(preview).getByText("Волжский институт")).toBeTruthy();
  });

  it("shows a server file error next to the picker", async () => {
    mockApi(
      importHandlers({
        "POST /imports": () =>
          apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
            { field: "file", message: "Файл повреждён или пуст" },
          ]),
      }),
    );
    renderApp("/imports");
    await chooseFile(xlsx());
    fireEvent.click(screen.getByRole("button", { name: /Загрузить файл/ }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Файл повреждён или пуст (код VALIDATION_ERROR)");
    expect(screen.getByLabelText("Выберите файл").getAttribute("aria-describedby")).toContain(alert.id);
  });
});

describe("imports: mapping and check", () => {
  it("does not allow one header for two fields", async () => {
    mockApi(importHandlers());
    renderApp("/imports");
    await uploadFile();
    const comment = screen.getByLabelText("Комментарий") as HTMLSelectElement;
    const taken = within(comment).getByRole("option", { name: /Вендор \(выбран для «Вендор»\)/ }) as HTMLOptionElement;
    expect(taken.disabled).toBe(true);
    fireEvent.change(comment, { target: { value: "Вендор" } });
    expect(comment.value).toBe("");
    fireEvent.change(comment, { target: { value: "Примечание" } });
    expect(comment.value).toBe("Примечание");
    const valid = within(screen.getByLabelText("Срок действия лицензии")).getByRole("option", {
      name: /Примечание/,
    }) as HTMLOptionElement;
    expect(valid.disabled).toBe(true);
  });

  it("sends the full mapping, renders the report and filters errors", async () => {
    const api = mockApi(importHandlers());
    renderApp("/imports");
    await checkMapping();
    expect(await screen.findByText("Корректных")).toBeTruthy();
    expect(api.calls.find((c) => c.path === "/imports/4/check")?.body).toEqual({
      mapping: { ...UPLOAD.mapping },
    });
    expect(currentStep()).toContain("Проверка");
    expect(screen.getByText("Д-007")).toBeTruthy();
    expect(screen.getByText("обновление")).toBeTruthy();
    expect(screen.getByText("Менеджер не найден среди пользователей CRM")).toBeTruthy();

    const errors = screen.getByRole("button", { name: /^Ошибки/ });
    fireEvent.click(errors);
    expect(errors.getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByText("Д-001")).toBeNull();
    expect(screen.getByText("Не заполнено поле «Номер договора»")).toBeTruthy();
  });

  it("shows mapping errors from the server with a way back to the mapping", async () => {
    mockApi(
      importHandlers({
        "POST /imports/4/check": () =>
          apiError(422, "VALIDATION_ERROR", "Проверьте заполненные поля", [
            { field: "mapping", message: "Столбец «ИТ-продукт» отсутствует в файле" },
          ]),
      }),
    );
    renderApp("/imports");
    await checkMapping();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Столбец «ИТ-продукт» отсутствует в файле");
    fireEvent.click(within(alert).getByRole("button", { name: /Вернуться к сопоставлению/ }));
    await waitFor(() => expect(currentStep()).toContain("Сопоставление"));
    expect(screen.getByLabelText("Наименование вуза")).toBeTruthy();
  });

  it("requires a column for every required field before checking", async () => {
    const api = mockApi(importHandlers());
    renderApp("/imports");
    const university = await uploadFile();
    fireEvent.change(university, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));
    expect((await screen.findByRole("alert")).textContent).toContain("«Наименование вуза»");
    expect(api.count("POST", "/imports/4/check")).toBe(0);
  });
});

describe("imports: apply", () => {
  it("confirms with counts, applies and refreshes dependent data", async () => {
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    const api = mockApi(importHandlers({ "POST /imports/4/apply": () => REPORT }));
    renderApp("/imports");
    await checkMapping();
    fireEvent.click(await screen.findByRole("button", { name: "Применить загрузку" }));
    const dialog = await screen.findByRole("dialog", { name: "Применить загрузку?" });
    expect(dialog.textContent).toContain("Будет записано строк: 2, из них с предупреждениями: 1");
    expect(dialog.textContent).toContain("строки с ошибками: 1");
    expect(api.count("POST", "/imports/4/apply")).toBe(0);
    invalidate.mockClear();

    fireEvent.click(within(dialog).getByRole("button", { name: "Применить" }));
    expect(await screen.findByText(/Загрузка «реестр\.xlsx» применена/)).toBeTruthy();
    expect(api.calls.find((c) => c.path === "/imports/4/apply")).toMatchObject({
      body: { mapping: UPLOAD.mapping },
      headers: { "x-csrf-token": CSRF_TOKEN },
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(currentStep()).toContain("Применение");
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    for (const key of [["contracts"], ["universities"], ["it-products"], ["it-directions"], ["audit"], ["imports"]]) {
      expect(keys).toContain(JSON.stringify(key));
    }
  });

  it("explains that an upload was already applied", async () => {
    mockApi(
      importHandlers({
        "POST /imports/4/apply": () =>
          apiError(409, "CONFLICT", "Конфликт данных: запись изменена или уже существует"),
      }),
    );
    renderApp("/imports");
    await checkMapping();
    fireEvent.click(await screen.findByRole("button", { name: "Применить загрузку" }));
    const dialog = await screen.findByRole("dialog", { name: "Применить загрузку?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Применить" }));
    const alert = await screen.findByText(/Эта загрузка уже применена/);
    expect(alert.textContent).toContain("код CONFLICT");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect((screen.getByRole("button", { name: "Применить загрузку" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("imports: history", () => {
  it("lists uploads and opens the report of one", async () => {
    const api = mockApi(
      importHandlers({
        "GET /imports": () => [
          {
            id: 4,
            filename: "реестр.xlsx",
            status: "applied",
            row_count: 3,
            created_at: "2026-09-16T02:10:00Z",
            created_by: { id: 2, full_name: "Павел Демо" },
            applied_at: "2026-09-16T02:20:00Z",
            summary: REPORT.summary,
          },
        ],
        "GET /imports/4": () => ({ ...UPLOAD, status: "applied", report: REPORT }),
      }),
    );
    renderApp("/imports");
    const history = (await screen.findByRole("heading", { name: "История загрузок" })).closest(
      "section",
    ) as HTMLElement;
    const item = await within(history).findByRole("button", { name: /реестр\.xlsx/ });
    expect(item.textContent).toContain("применён");
    expect(item.textContent).toContain("Павел Демо");
    expect(item.textContent).toContain("корректных: 2");
    fireEvent.click(item);
    const dialog = await screen.findByRole("dialog", { name: "Загрузка «реестр.xlsx»" });
    expect(await within(dialog).findByText("Отчёт применения")).toBeTruthy();
    expect(within(dialog).getByText("Д-007")).toBeTruthy();
    expect(api.count("GET", "/imports/4")).toBe(1);
  });
});
