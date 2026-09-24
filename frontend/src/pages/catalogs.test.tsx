import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  CSRF_TOKEN,
  apiError,
  mockApi,
  renderApp,
  sessionFixture,
} from "../test/utils";
import { NO_UNIVERSITIES_TEXT } from "./UniversitiesPage";

const asManager = () => ({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
const location = () => screen.getByTestId("location").textContent ?? "";
const sectionOf = async (heading: string) =>
  (await screen.findByRole("heading", { name: heading })).closest("section") as HTMLElement;
const change = (el: HTMLElement, value: string) =>
  fireEvent.change(el, { target: { value } });

describe("navigation", () => {
  it("lists contracts and catalogs in the sidebar and keeps universities active on a detail page", async () => {
    mockApi();
    renderApp("/universities/1");
    expect(await screen.findByRole("link", { name: /Договоры/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Справочники/ }).getAttribute("href")).toBe("/catalogs");
    const universities = screen.getByRole("link", { name: /Учебные заведения/ });
    expect(universities.className).toContain("active");
    // The heading "create" button is only on the list page.
    expect(screen.queryByRole("button", { name: /Добавить заведение/ })).toBeNull();
  });
});

describe("catalogs page", () => {
  it("shows create, edit and deactivate controls to a supervisor", async () => {
    mockApi();
    renderApp("/catalogs");
    expect(await screen.findByRole("button", { name: "Изменить направление DevOps" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Добавить направление/ })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Деактивировать" })).toHaveLength(2);
  });

  it("is read-only for a crm-user", async () => {
    mockApi(asManager());
    renderApp("/catalogs?tab=products");
    expect(await screen.findByText("Учебная среда")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Добавить продукт/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Изменить/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Деактивировать" })).toBeNull();
  });

  it("switches tabs with the keyboard", async () => {
    mockApi();
    renderApp("/catalogs");
    const directions = await screen.findByRole("tab", { name: "ИТ-направления" });
    expect(directions.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(directions, { key: "ArrowRight" });
    const products = screen.getByRole("tab", { name: "ИТ-продукты" });
    await waitFor(() => expect(products.getAttribute("aria-selected")).toBe("true"));
    expect(document.activeElement).toBe(products);
    expect(location()).toBe("/catalogs?tab=products");
  });

  it("filters products by direction on the server and shows direction chips", async () => {
    const api = mockApi();
    renderApp("/catalogs?tab=products");
    const row = (await screen.findByText("Учебная среда")).closest("tr") as HTMLElement;
    expect(within(row).getByRole("listitem").textContent).toBe("DevOps");
    const select = screen.getByLabelText("Направление");
    await within(select).findByRole("option", { name: "Тестирование" });
    change(select, "2");
    await waitFor(() => expect(api.count("GET", "/it-products?direction_id=2")).toBe(1));
  });

  it("deactivates a direction with PATCH is_active=false", async () => {
    const api = mockApi({
      "PATCH /it-directions/1": () => ({ ...api.data.directions[0], is_active: false }),
    });
    renderApp("/catalogs");
    const row = (await screen.findByText("DevOps")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Деактивировать" }));
    await waitFor(() => expect(api.count("PATCH", "/it-directions/1")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")).toMatchObject({
      body: { is_active: false },
      headers: { "x-csrf-token": CSRF_TOKEN },
    });
    await waitFor(() => expect(api.count("GET", "/it-directions")).toBe(2));
  });

  it("creates a product with the selected directions", async () => {
    const api = mockApi({ "POST /it-products": () => [201, api.data.products[0]] });
    renderApp("/catalogs?tab=products");
    fireEvent.click(await screen.findByRole("button", { name: /Добавить продукт/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новый ИТ-продукт" });
    change(within(dialog).getByLabelText("Вендор"), "Вендор");
    change(within(dialog).getByLabelText("Программное обеспечение"), "Продукт");
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: "Тестирование" }));
    fireEvent.submit(dialog.querySelector("form")!);
    await waitFor(() => expect(api.count("POST", "/it-products")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      vendor: "Вендор",
      name: "Продукт",
      description: "",
      direction_ids: [2],
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("universities", () => {
  it("shows short name, place, a safe website link and managers", async () => {
    mockApi();
    renderApp("/universities");
    const card = (await screen.findByText("Колледж связи")).closest("tr") as HTMLElement;
    expect(within(card).getByText("КС")).toBeTruthy();
    expect(within(card).getByText(/Казань, Республика Татарстан/)).toBeTruthy();
    const link = within(card).getByRole("link", { name: /ks\.example/ });
    expect(link.getAttribute("href")).toBe("https://ks.example/");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(within(card).getByText(/Анна Демо/)).toBeTruthy();
    expect(within(card).getByRole("link", { name: /Колледж связи/ }).getAttribute("href")).toBe(
      "/universities/1",
    );
    expect(within(card).getByRole("button", { name: "Изменить Колледж связи" })).toBeTruthy();
  });

  it("does not render javascript: websites as links", async () => {
    const api = mockApi({
      "GET /universities": () => [{ ...api.data.universities[0], website: "javascript:alert(1)" }],
    });
    renderApp("/universities");
    const card = (await screen.findByText("Колледж связи")).closest("tr") as HTMLElement;
    expect(within(card).queryAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "/universities/1",
    ]);
  });

  it("explains the empty list to a manager without assigned universities", async () => {
    mockApi({ ...asManager(), "GET /universities": () => [] });
    renderApp("/universities");
    expect(await screen.findByText(NO_UNIVERSITIES_TEXT)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Добавить заведение/ })).toBeNull();
  });

  it("explains the empty contracts list to a manager without assigned universities", async () => {
    const api = mockApi({ ...asManager(), "GET /universities": () => [] });
    renderApp("/contracts");
    expect(await screen.findByText(NO_UNIVERSITIES_TEXT)).toBeTruthy();
    expect(screen.queryByLabelText("Менеджер")).toBeNull();
    expect(api.count("GET", "/users?role=crm-user")).toBe(0);
  });

  it("assigns managers by sending the full user_ids list", async () => {
    const api = mockApi({
      "PUT /universities/1/managers": () => ({
        ...api.data.universities[0],
        managers: [
          { id: 5, full_name: "Анна Демо" },
          { id: 6, full_name: "Олег Кузнецов" },
        ],
      }),
    });
    renderApp("/universities/1");
    const managers = await sectionOf("Ответственные от ИТ-школы");
    fireEvent.click(within(managers).getByRole("button", { name: /Изменить/ }));
    const dialog = await screen.findByRole("dialog", { name: "Ответственные от ИТ-школы" });
    const anna = (await within(dialog).findByRole("checkbox", { name: /Анна Демо/ })) as HTMLInputElement;
    expect(anna.checked).toBe(true);
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Олег Кузнецов/ }));
    const listCalls = api.callsTo("GET", "/universities").length;
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(api.count("PUT", "/universities/1/managers")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")).toMatchObject({
      body: { user_ids: [5, 6] },
      headers: { "x-csrf-token": CSRF_TOKEN },
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(api.callsTo("GET", "/universities").length).toBeGreaterThan(listCalls));
  });

  it("lets a crm-user manage contacts but not managers or the university", async () => {
    mockApi(asManager());
    renderApp("/universities/1");
    const managers = await sectionOf("Ответственные от ИТ-школы");
    expect(within(managers).queryByRole("button", { name: /Изменить/ })).toBeNull();
    expect(within(managers).getByText("Анна Демо")).toBeTruthy();
    const contacts = await sectionOf("Ответственные от вуза");
    expect(await within(contacts).findByText("Иван Демо")).toBeTruthy();
    expect(within(contacts).getByRole("button", { name: /Добавить/ })).toBeTruthy();
    expect(within(contacts).getByRole("button", { name: "Изменить контакт Иван Демо" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Деактивировать" })).not.toBeNull();
    const card = await sectionOf("Колледж связи");
    expect(within(card).queryByRole("button", { name: /Изменить/ })).toBeNull();
  });

  it("shows the contracts of the university only", async () => {
    const api = mockApi();
    renderApp("/universities/1");
    const contracts = await sectionOf("Договоры");
    expect(await within(contracts).findByText("Д-2026-001")).toBeTruthy();
    expect(api.count("GET", "/contracts?university_id=1&limit=50&offset=0")).toBe(1);
  });

  it("reports a university outside the scope", async () => {
    mockApi();
    renderApp("/universities/99");
    expect(
      await screen.findByText("Учебное заведение не найдено или у вас нет к нему доступа."),
    ).toBeTruthy();
  });
});

describe("contracts page", () => {
  it("renders rows with the expiry badge, status label and contacts", async () => {
    mockApi();
    renderApp("/contracts");
    const row = (await screen.findByText("Д-2026-001")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Истекает")).toBeTruthy();
    expect(within(row).getByText("Идёт передача")).toBeTruthy();
    expect(within(row).getByText("Иван Демо")).toBeTruthy();
    expect(within(row).getByText("01.10.2026")).toBeTruthy();
  });

  it("keeps the field filters behind «Фильтры» until asked, and counts the applied ones", async () => {
    mockApi();
    renderApp("/contracts");
    const toggle = await screen.findByRole("button", { name: /Фильтры/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("group", { name: "Фильтры договоров" })).toBeNull();

    fireEvent.click(toggle);
    const filters = await screen.findByRole("group", { name: "Фильтры договоров" });
    change(within(filters).getByLabelText("Подписан с"), "2026-01-01");
    expect(await screen.findByLabelText("Применено фильтров: 1")).toBeTruthy();
  });

  it("reads filters from the URL and writes changes to the URL and the request", async () => {
    const api = mockApi();
    renderApp("/contracts?transfer_status=in_progress&offset=50");
    await waitFor(() =>
      expect(api.count("GET", "/contracts?transfer_status=in_progress&limit=50&offset=50")).toBe(1),
    );
    const filters = screen.getByRole("group", { name: "Фильтры договоров" });
    const university = within(filters).getByLabelText("Учебное заведение");
    await within(university).findByRole("option", { name: "КС" });
    change(university, "1");

    await waitFor(() =>
      expect(location()).toBe("/contracts?transfer_status=in_progress&university_id=1"),
    );
    await waitFor(() =>
      expect(
        api.count("GET", "/contracts?university_id=1&transfer_status=in_progress&limit=50&offset=0"),
      ).toBe(1),
    );

    change(within(filters).getByLabelText("Подписан с"), "2026-01-01");
    await within(within(filters).getByLabelText("Менеджер")).findByRole("option", {
      name: "Олег Кузнецов",
    });
    change(within(filters).getByLabelText("Менеджер"), "6");
    fireEvent.change(screen.getByRole("textbox", { name: "Поиск" }), {
      target: { value: "Д-2026" },
    });
    const expected =
      "/contracts?q=%D0%94-2026&university_id=1&manager_user_id=6&transfer_status=in_progress&signed_from=2026-01-01&limit=50&offset=0";
    await waitFor(() => expect(api.count("GET", expected)).toBe(1));
    const url = new URLSearchParams(location().split("?")[1]);
    expect(Object.fromEntries(url)).toEqual({
      transfer_status: "in_progress",
      university_id: "1",
      signed_from: "2026-01-01",
      manager_user_id: "6",
      q: "Д-2026",
    });
  });

  it("ignores the manager filter from the URL for a crm-user", async () => {
    const api = mockApi(asManager());
    renderApp("/contracts?manager_user_id=6");
    await screen.findByText("Д-2026-001");
    expect(api.count("GET", "/contracts?limit=50&offset=0")).toBe(1);
  });

  it("previews the default validity date", async () => {
    mockApi();
    renderApp("/contracts");
    fireEvent.click(await screen.findByRole("button", { name: /Новый договор/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новый договор" });
    expect(within(dialog).getByText(/по умолчанию — через год после подписания/)).toBeTruthy();
    change(within(dialog).getByLabelText("Дата подписания"), "2024-02-29");
    expect(within(dialog).getByTestId("validity-preview").textContent).toBe("28.02.2025");
    change(within(dialog).getByLabelText("Действует до"), "2024-12-31");
    expect(within(dialog).queryByTestId("validity-preview")).toBeNull();
  });

  it("maps a CONFLICT to the contract number field and sends the form data", async () => {
    const api = mockApi({
      "POST /contracts": () =>
        apiError(409, "CONFLICT", "Договор с таким номером уже существует", [
          { field: "contract_number", message: "Номер договора уже используется", type: "unique" },
        ]),
    });
    renderApp("/contracts");
    fireEvent.click(await screen.findByRole("button", { name: /Новый договор/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новый договор" });
    const form = dialog.querySelector("form")!;
    const university = within(dialog).getByLabelText("Учебное заведение");
    await within(university).findByRole("option", { name: "Колледж связи" });
    await within(dialog).findByRole("option", { name: "РТК ИТ — Учебная среда" });
    await within(dialog).findByRole("option", { name: "Идёт передача" });
    change(within(dialog).getByLabelText("Номер договора"), " Д-2026-001 ");
    change(university, "1");
    change(within(dialog).getByLabelText("ИТ-продукт"), "3");
    change(within(dialog).getByLabelText("Дата подписания"), "2026-01-15");
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: "Иван Демо" }));
    fireEvent.submit(form);

    await waitFor(() => expect(api.count("POST", "/contracts")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      contract_number: "Д-2026-001",
      university_id: 1,
      it_product_id: 3,
      signed_at: "2026-01-15",
      transfer_status: "not_started",
      contact_ids: [7],
      comment: "",
    });
    const message = await within(dialog).findByText("Номер договора уже используется");
    expect(message.closest("label")?.querySelector("input")?.name).toBe("contract_number");
    expect(within(dialog).getByRole("alert").textContent).toBe(
      "Договор с таким номером уже существует (код CONFLICT)",
    );
  });

  it("limits contacts to the chosen university and clears them on change", async () => {
    mockApi();
    renderApp("/contracts");
    fireEvent.click(await screen.findByRole("button", { name: /Новый договор/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новый договор" });
    expect(within(dialog).getByText("Сначала выберите учебное заведение.")).toBeTruthy();
    const university = within(dialog).getByLabelText("Учебное заведение");
    await within(university).findByRole("option", { name: "Технический университет" });
    change(university, "1");
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: "Иван Демо" }));
    change(university, "2");
    expect(
      await within(dialog).findByText("У учебного заведения нет активных контактов."),
    ).toBeTruthy();
    expect(within(dialog).queryByRole("checkbox")).toBeNull();
  });

  it("edits a contract with PATCH and refreshes the contracts list and recent actions", async () => {
    const api = mockApi({
      "PATCH /contracts/12": () => api.data.contracts[0],
    });
    renderApp("/contracts");
    fireEvent.click(await screen.findByRole("button", { name: "Изменить договор Д-2026-001" }));
    const dialog = await screen.findByRole("dialog", { name: "Договор Д-2026-001" });
    await within(dialog).findByRole("checkbox", { name: "Иван Демо" });
    change(within(dialog).getByLabelText("Комментарий"), "Продлить");
    const audit = api.callsTo("GET", "/audit/recent").length;
    fireEvent.submit(dialog.querySelector("form")!);
    await waitFor(() => expect(api.count("PATCH", "/contracts/12")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      contract_number: "Д-2026-001",
      university_id: 1,
      it_product_id: 3,
      signed_at: "2025-10-01",
      valid_until: "2026-10-01",
      transfer_status: "in_progress",
      contact_ids: [7],
      comment: "Продлить",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(api.callsTo("GET", "/contracts").length).toBe(2));
    // Recent actions are not mounted on this page: invalidated, not refetched.
    expect(api.callsTo("GET", "/audit/recent").length).toBe(audit);
  });
});
