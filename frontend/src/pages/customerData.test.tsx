import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../test/utils";

const company = { id: 1, name: "ООО «ТДата»", is_active: true };
const contact = {
  id: 2, company_id: 1, full_name: "Тестовый Контакт", phone: "00123", email: "contact@example.test",
  preferred_channels: ["Почта", "Чат в ТГ"], product_ids: [3, 4], is_active: true,
};
const learner = { id: 7, last_name: "Тестов", first_name: "Иван", middle_name: "", phone: "00123", email: "learner@example.test" };
const application = {
  id: 9, external_number: "A-1", course: "Python", stream_number: "3",
  learner_id: 7, learner_name: "Тестов Иван", payment_status: "unconfirmed_by_data",
  payment_status_label: "Не подтверждено данными",
};

describe("customer data pages", () => {
  it("shows product contacts and creates a supplier company", async () => {
    const api = mockApi({
      "GET /it-products": () => [{ id: 3, vendor: company.name, name: "RT.DataLake", description: "",
        is_active: true, directions: [], company_id: 1, vendor_contacts: [contact] }],
      "GET /vendor-companies": () => [company],
      "GET /vendor-contacts": () => [contact],
      "POST /vendor-companies": () => [201, { id: 5, name: "Новая компания", is_active: true }],
    });
    renderApp("/catalogs?tab=products");
    expect(await screen.findByText("Тестовый Контакт")).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: /Компании/ }));
    expect(await screen.findByRole("button", { name: company.name })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Добавить компанию" }));
    const dialog = await screen.findByRole("dialog", { name: "Новая компания" });
    fireEvent.change(within(dialog).getByLabelText("Название компании"), { target: { value: "Новая компания" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.count("POST", "/vendor-companies")).toBe(1));
  });

  it("assigns a contact to selected products and keeps communication channels as labels", async () => {
    const api = mockApi({
      "GET /vendor-companies": () => [company],
      "GET /vendor-contacts": () => [],
      "GET /it-products": () => [{ id: 3, vendor: company.name, name: "RT.DataLake", company_id: 1,
        is_active: true, description: "", directions: [], vendor_contacts: [] }],
      "POST /vendor-contacts": () => [201, contact],
    });
    renderApp("/vendors");
    fireEvent.click(await screen.findByRole("button", { name: "Добавить контакт" }));
    const dialog = await screen.findByRole("dialog", { name: "Новый контакт" });
    fireEvent.change(within(dialog).getByLabelText("ФИО"), { target: { value: "Тестовый Контакт" } });
    fireEvent.change(within(dialog).getByLabelText("Предпочтительные способы связи"), { target: { value: "Почта; Чат в ТГ" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "RT.DataLake" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.count("POST", "/vendor-contacts")).toBe(1));
    expect(api.calls.find((call) => call.method === "POST")?.body).toMatchObject({
      company_id: 1, product_ids: [3], preferred_channels: ["Почта", "Чат в ТГ"],
    });
  });

  it("keeps a learner summary safe for managers and opens full details for supervisors", async () => {
    const managerApi = mockApi({
      "GET /auth/me": () => sessionFixture(["crm-user"]),
      "GET /learners": () => [learner],
    });
    renderApp("/learners");
    expect(await screen.findByText("Тестов Иван")).toBeTruthy();
    expect(screen.queryByText("Паспорт")).toBeNull();
    expect(screen.queryByRole("button", { name: "Открыть анкету" })).toBeNull();
    expect(managerApi.count("GET", "/learners/7")).toBe(0);
  });

  it("shows a full learner card only after an authorized detail request", async () => {
    const api = mockApi({
      "GET /learners": () => [learner],
      "GET /learners/7": () => ({ ...learner, snils: "001-234-567 89", passport_number: "000123",
        education: "Высшее" }),
    });
    renderApp("/learners");
    fireEvent.click(await screen.findByRole("button", { name: "Открыть анкету" }));
    const dialog = await screen.findByRole("dialog", { name: "Анкета слушателя" });
    expect(await within(dialog).findByDisplayValue("000123")).toBeTruthy();
    expect(api.count("GET", "/learners/7")).toBe(1);
  });

  it("creates an incomplete learner profile with only names", async () => {
    const api = mockApi({
      "GET /learners": () => [],
      "POST /learners": () => [201, learner],
    });
    renderApp("/learners");
    fireEvent.click(await screen.findByRole("button", { name: "Добавить слушателя" }));
    const dialog = await screen.findByRole("dialog", { name: "Новая анкета слушателя" });
    fireEvent.change(within(dialog).getByLabelText("Фамилия"), { target: { value: "Тестов" } });
    fireEvent.change(within(dialog).getByLabelText("Имя"), { target: { value: "Иван" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить анкету" }));
    await waitFor(() => expect(api.count("POST", "/learners")).toBe(1));
    expect(api.calls.find((call) => call.method === "POST")?.body).toEqual({ last_name: "Тестов", first_name: "Иван" });
  });

  it("filters applications by course and shows unconfirmed payment state", async () => {
    const api = mockApi({ "GET /course-applications": () => [application] });
    renderApp("/applications");
    expect(await screen.findByText("Не подтверждено данными")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Курс"), { target: { value: "Python" } });
    fireEvent.click(screen.getByRole("button", { name: "Найти" }));
    await waitFor(() => expect(api.calls.some((call) => call.path.includes("course=Python"))).toBe(true));
  });

  it("previews an import before enabling apply", async () => {
    const report = { summary: { rows: 2, valid: 1, invalid: 0, skipped: 1, created: 1, updated: 0 },
      rows: [{ row_number: 1, status: "ok", action: "created", errors: [], warnings: [], candidate_ids: [] },
        { row_number: 2, status: "skipped", action: null, errors: [], warnings: ["Значение null пропущено"], candidate_ids: [] }] };
    const api = mockApi({
      "POST /customer-imports/applications/preview": () => report,
      "POST /customer-imports/applications/apply": () => report,
    });
    renderApp("/customer-imports");
    expect(screen.queryByRole("button", { name: "Применить" })).toBeNull();
    fireEvent.change(await screen.findByLabelText("Файл"), { target: { files: [new File(["[]"], "заявки.json", { type: "application/json" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(await screen.findByText("Значение null пропущено")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    await waitFor(() => expect(api.count("POST", "/customer-imports/applications/apply")).toBe(1));
  });

  it("allows applying a file after resolving its only ambiguous learner", async () => {
    const report = { summary: { rows: 1, valid: 0, invalid: 1, skipped: 0, created: 0, updated: 0 },
      rows: [{ row_number: 1, status: "error", action: null,
        errors: ["Неоднозначное совпадение слушателей; требуется ручное разрешение"],
        warnings: [], candidate_ids: [7] }] };
    const api = mockApi({
      "GET /learners": () => [learner],
      "POST /customer-imports/applications/preview": () => report,
      "POST /customer-imports/applications/apply": () => ({ ...report,
        summary: { ...report.summary, valid: 1, invalid: 0 },
        rows: [{ ...report.rows[0], status: "ok", errors: [], candidate_ids: [] }] }),
    });
    renderApp("/customer-imports");
    fireEvent.change(await screen.findByLabelText("Файл"), { target: { files: [new File(["[]"], "заявки.json")] } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    const apply = await screen.findByRole("button", { name: "Применить" });
    expect((apply as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Слушатель"), { target: { value: "7" } });
    expect((apply as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(apply);
    await waitFor(() => expect(api.count("POST", "/customer-imports/applications/apply")).toBe(1));
    const body = api.calls.find((call) => call.path.includes("/customer-imports/applications/apply"))?.body;
    expect((body as FormData).get("resolved_learner_ids")).toBe('{"1":7}');
  });

  it("shows template mapping, omissions, row warnings, and safe history", async () => {
    const report = { template_version: "customer-learners-v1", mapping: { last_name: "Фамилия", first_name: "Имя" },
      unmapped_headers: ["Дополнительное поле"],
      summary: { rows: 1, valid: 1, invalid: 0, skipped: 0, created: 1, updated: 0 },
      rows: [{ row_number: 2, status: "ok", action: "created", errors: [],
        warnings: ["Телефон был числом Excel; проверьте исходную ячейку"], candidate_ids: [],
        signals: [{ rule_code: "document_identifier_reuse", priority: "high" }] }],
      batch_signals: [{ rule_code: "import_velocity", priority: "medium" }] };
    mockApi({
      "GET /customer-imports/history": () => [{ id: 5, kind: "learners", created_at: "2026-09-26T12:00:00Z",
        template_version: "customer-learners-v1", summary: report.summary }],
      "POST /customer-imports/learners/preview": () => report,
      "POST /customer-imports/learners/apply": () => ({ ...report, batch_id: 6,
        record_links: [{ row_number: 2, entity_type: "learner", entity_id: 7, action: "created" }] }),
    });
    renderApp("/customer-imports");
    expect(await screen.findByText(/Пакет 5/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Вид данных"), { target: { value: "learners" } });
    fireEvent.change(screen.getByLabelText("Файл"), { target: { files: [new File(["demo"], "demo.xlsx")] } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(await screen.findByText(/2 столбца распознано/)).toBeTruthy();
    expect(screen.getByText(/Не перенесены: Дополнительное поле/)).toBeTruthy();
    expect(screen.getByText(/Телефон был числом Excel/)).toBeTruthy();
    expect(screen.getByText(/Повтор документа \(высокий\)/)).toBeTruthy();
    expect(screen.getByText(/Необычный объём загрузок \(средний\)/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    expect((await screen.findByRole("link", { name: /Открыть карточку/ }) as HTMLAnchorElement).pathname).toBe("/learners");
  });

  it("disables apply for a header-only template", async () => {
    mockApi({ "POST /customer-imports/learners/preview": () => ({
      template_version: "customer-learners-v1", mapping: { last_name: "Фамилия", first_name: "Имя" },
      unmapped_headers: [], summary: { rows: 0, valid: 0, invalid: 0, skipped: 0, created: 0, updated: 0 }, rows: [],
    }) });
    renderApp("/customer-imports");
    fireEvent.change(await screen.findByLabelText("Вид данных"), { target: { value: "learners" } });
    fireEvent.change(screen.getByLabelText("Файл"), { target: { files: [new File(["demo"], "blank.xlsx")] } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect((await screen.findByRole("button", { name: "Применить" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("requires a second preview for duplicate columns and keeps the approved choice for apply", async () => {
    const summary = { rows: 1, valid: 1, invalid: 0, skipped: 0, created: 1, updated: 0 };
    const row = { row_number: 2, status: "ok", action: "created", errors: [], warnings: [], candidate_ids: [] };
    const mapping = { last_name: "Фамилия", first_name: "Имя", phone: "Телефон" };
    let previews = 0;
    const api = mockApi({
      "POST /customer-imports/learners/preview": () => ({ summary, rows: [row], mapping,
        unmapped_headers: ["Номер телефона"],
        mapping_conflicts: ++previews === 1 ? { phone: ["Телефон", "Номер телефона"] } : {} }),
      "POST /customer-imports/learners/apply": () => ({ summary, rows: [row] }),
    });
    renderApp("/customer-imports");
    fireEvent.change(await screen.findByLabelText("Вид данных"), { target: { value: "learners" } });
    fireEvent.change(screen.getByLabelText("Файл"), { target: { files: [new File(["demo"], "synthetic.xlsx")] } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect((await screen.findByRole("button", { name: "Применить" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Проверить сопоставление" }));
    await waitFor(() => expect(previews).toBe(2));
    expect((screen.getByRole("button", { name: "Применить" }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    await waitFor(() => expect(api.count("POST", "/customer-imports/learners/apply")).toBe(1));
    const body = api.calls.find((call) => call.path.includes("/customer-imports/learners/apply"))?.body as FormData;
    expect(JSON.parse(body.get("mapping") as string)).toEqual(mapping);
  });
});
