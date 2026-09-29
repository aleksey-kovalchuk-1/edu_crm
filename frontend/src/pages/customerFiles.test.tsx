import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ImportReport, ImportUpload } from "../api/imports";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

/* The customer's applications JSON and workbook in «Загрузка справочников» (D-247). */

const FIELDS = [{ name: "university_name", label: "Наименование вуза", required: true }];

const JSON_UPLOAD: ImportUpload = {
  id: 7,
  kind: "applications",
  filename: "Данные оплат.json",
  status: "uploaded",
  header_row: 0,
  headers: ["Номер заявки", "Курс", "Номер потока"],
  mapping: {},
  row_count: 3,
  preview: [
    { row_number: 1, cells: [null, null, null] },
    { row_number: 2, cells: ["ORD-TEST-0001", "Анализ данных", "1"] },
  ],
  created_at: "2026-09-29T10:00:00Z",
  created_by: { id: 2, full_name: "Павел Демо" },
  report: null,
};

const JSON_REPORT: ImportReport = {
  summary: {
    rows: 3, valid: 2, invalid: 0, skipped: 1, with_warnings: 0,
    created: { course_applications: 1 }, updated: { course_applications: 1 },
  },
  rows: [
    { row_number: 1, key: "", status: "skipped", action: null, errors: [], warnings: ["Пустая запись (null) пропущена"] },
    { row_number: 2, key: "ORD-TEST-0001", status: "ok", action: "create", errors: [], warnings: [] },
    { row_number: 3, key: "ORD-TEST-0002", status: "ok", action: "update", errors: [], warnings: [] },
  ],
};

const WORKBOOK_UPLOAD: ImportUpload = {
  ...JSON_UPLOAD,
  id: 8,
  kind: "workbook",
  filename: "RTK_IT_School_CRM_20.xlsx",
  headers: [],
  row_count: 2,
  preview: [{ row_number: 4, cells: ["Вузы", "UNI-001", "Московский физико-технический институт"] }],
  sheets: [
    { name: "Сводка", status: "service", rows: 1, reason: "Служебный лист книги; не загружается" },
    { name: "Вузы", status: "supported", rows: 2, reason: "" },
    { name: "Программы", status: "not_supported", rows: 80, reason: "В CRM нет сущности для этих данных; лист не загружается" },
  ],
};

const WORKBOOK_REPORT: ImportReport = {
  summary: {
    rows: 2, valid: 1, invalid: 0, skipped: 1, with_warnings: 0,
    created: { universities: 0 }, updated: { universities: 1 },
  },
  rows: [
    { sheet: "Вузы", row_number: 4, key: "UNI-001", status: "ok", action: "update", errors: [], warnings: [] },
    { sheet: "Вузы", row_number: 5, key: "UNI-002", status: "skipped", action: null, errors: [],
      warnings: ["Вуз «Неизвестный университет» не найден в каталоге CRM; строка пропущена, вуз не создан"] },
  ],
  unmatched_universities: [{ external_id: "UNI-002", name: "Неизвестный университет", short_name: "НУ" }],
  sheets: WORKBOOK_UPLOAD.sheets,
};

async function upload(name: string) {
  const input = await screen.findByLabelText("Выберите файл");
  fireEvent.change(input, { target: { files: [new File(["data"], name)] } });
  fireEvent.click(screen.getByRole("button", { name: /Загрузить файл/ }));
}

describe("imports: customer files", () => {
  it("accepts a .json file and skips the column mapping", async () => {
    const api = mockApi({
      "GET /imports/fields": () => FIELDS,
      "GET /imports": () => [],
      "POST /imports": () => [201, JSON_UPLOAD],
      "POST /imports/7/check": () => JSON_REPORT,
    });
    renderApp("/imports");
    await upload("Данные оплат.json");
    expect(await screen.findByRole("heading", { name: "Состав файла" })).toBeTruthy();
    expect(screen.getByText(/ФИО, телефоны и почта не читаются и не сохраняются/)).toBeTruthy();
    expect(screen.queryByLabelText("Наименование вуза")).toBeNull();
    const preview = screen.getByRole("region", { name: "Первые записи" });
    expect(within(preview).getByText("ORD-TEST-0001")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));
    // Shown under both «Будет создано» and «Будет обновлено».
    expect(await screen.findAllByText("Заявки (номер, курс, поток)")).toHaveLength(2);
    expect(screen.getByRole("columnheader", { name: "Номер заявки" })).toBeTruthy();
    expect(screen.getByText("Пустая запись (null) пропущена")).toBeTruthy();
    const check = api.calls.find((c) => c.method === "POST" && c.path === "/imports/7/check")!;
    expect(check.body).toEqual({ mapping: {} });
  });

  it("lists every workbook sheet and the universities that will be skipped", async () => {
    mockApi({
      "GET /imports/fields": () => FIELDS,
      "GET /imports": () => [],
      "POST /imports": () => [201, WORKBOOK_UPLOAD],
      "POST /imports/8/check": () => WORKBOOK_REPORT,
    });
    renderApp("/imports");
    await upload("RTK_IT_School_CRM_20.xlsx");
    expect(await screen.findByRole("heading", { name: "Состав файла" })).toBeTruthy();
    const sheets = screen.getByRole("table", { name: "Листы книги" });
    expect(within(sheets).getByText("Программы")).toBeTruthy();
    expect(within(sheets).getByText("не загружается")).toBeTruthy();
    expect(within(sheets).getByText("служебный")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));
    expect(await screen.findByText(/Не найдены в каталоге CRM — строки будут пропущены, вузы не создаются: 1/)).toBeTruthy();
    expect(screen.getByText("Неизвестный университет (НУ) · UNI-002")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Лист" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /К составу файла/ })).toBeTruthy();
  });

  it("tells an administrator that customer files are uploaded by the head", async () => {
    mockApi({
      "GET /auth/me": () => sessionFixture(["crm-admin"]),
      "GET /imports/fields": () => FIELDS,
      "GET /imports": () => [],
    });
    renderApp("/imports");
    expect(await screen.findByText(/Файлы заказчика .* загружает руководитель/)).toBeTruthy();
    expect(screen.queryByText(/Также принимаются файлы заказчика/)).toBeNull();
  });
});
