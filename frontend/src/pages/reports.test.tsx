import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp } from "../test/utils";

const OPTIONS = {
  owners: ["Ирина Петрова", "Олег Кузнецов"],
  statuses: [{ id: 11, name: "Первый контакт", workflow: "Типовое взаимодействие с вузом" }],
  columns: [
    { key: "university", label: "Учебное заведение", default: true },
    { key: "program", label: "Программа", default: true },
    { key: "it_product", label: "ИТ-продукт", default: true },
    { key: "owner", label: "Ответственный", default: true },
    { key: "students", label: "Обучающихся", default: false },
  ],
};

const PREVIEW = {
  columns: [
    { key: "university", label: "Учебное заведение" },
    { key: "program", label: "Программа" },
    { key: "it_product", label: "ИТ-продукт" },
    { key: "owner", label: "Ответственный" },
  ],
  rows: [{ university: "Колледж связи", program: "Аналитика данных", it_product: "РТК ИТ — Учебная среда", owner: "Ирина Петрова" }],
  total: 1,
};

const previewCalls = (api: ReturnType<typeof mockApi>) =>
  api.calls.filter((c) => c.method === "GET" && c.path.startsWith("/reports/interactions?")).map((c) => c.path);

function mockReports() {
  return mockApi({
    "GET /reports/options": () => OPTIONS,
    "GET /reports/interactions": () => PREVIEW,
  });
}

describe("reports page", () => {
  it("is in the sidebar and previews the default columns", async () => {
    const api = mockReports();
    renderApp("/reports");
    expect(await screen.findByRole("heading", { level: 1, name: "Отчёты" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Отчёты/ }).className).toContain("active");
    expect(await screen.findByText("Аналитика данных")).toBeTruthy();
    expect(screen.getByText("1 взаимодействие")).toBeTruthy();
    await waitFor(() => expect(previewCalls(api).at(-1)).toBe("/reports/interactions?column=university&column=program&column=it_product&column=owner"));
  });

  it("filters by a chosen owner and period, and the downloads carry the same query", async () => {
    const api = mockReports();
    renderApp("/reports");
    await screen.findByText("Аналитика данных");

    const owners = screen.getByRole("group", { name: "Ответственные" });
    fireEvent.click(within(owners).getByRole("checkbox", { name: "Олег Кузнецов" }));
    fireEvent.change(screen.getByLabelText("Период с"), { target: { value: "2026-09-01" } });

    await waitFor(() =>
      expect(previewCalls(api).at(-1)).toBe(
        "/reports/interactions?period_from=2026-09-01&owner=%D0%9E%D0%BB%D0%B5%D0%B3+%D0%9A%D1%83%D0%B7%D0%BD%D0%B5%D1%86%D0%BE%D0%B2&column=university&column=program&column=it_product&column=owner",
      ),
    );
    const pdf = screen.getByRole("link", { name: /PDF/ });
    expect(pdf.getAttribute("href")).toBe(
      "/api/v1/reports/interactions/export?format=pdf&period_from=2026-09-01&owner=%D0%9E%D0%BB%D0%B5%D0%B3+%D0%9A%D1%83%D0%B7%D0%BD%D0%B5%D1%86%D0%BE%D0%B2&column=university&column=program&column=it_product&column=owner",
    );
    expect(screen.getByRole("link", { name: /\.xlsx/ }).getAttribute("href")).toContain("format=xlsx");
    expect(screen.getByRole("link", { name: /\.xls\)/ }).getAttribute("href")).toContain("format=xls&");
  });

  it("adds a column in catalog order, not click order", async () => {
    const api = mockReports();
    renderApp("/reports");
    await screen.findByText("Аналитика данных");
    fireEvent.click(screen.getByRole("checkbox", { name: "Обучающихся" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Программа" }));
    await waitFor(() =>
      expect(previewCalls(api).at(-1)).toBe("/reports/interactions?column=university&column=it_product&column=owner&column=students"),
    );
  });

  it("blocks an inverted period and every download", async () => {
    mockReports();
    renderApp("/reports");
    await screen.findByText("Аналитика данных");
    fireEvent.change(screen.getByLabelText("Период с"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Период по"), { target: { value: "2026-09-01" } });
    expect(await screen.findByText("Конец периода раньше начала.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /PDF/ })).toBeNull();
    expect((screen.getByRole("button", { name: /PDF/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("interaction IT product link", () => {
  it("links an interaction to a catalog product from its page", async () => {
    const api = mockApi({ "PUT /launches/1/it-product": () => ({ ...api.data.launches[0], it_product_id: 3 }) });
    renderApp("/interactions/1");
    const select = (await screen.findByRole("combobox", { name: "ИТ-продукт из справочника" })) as HTMLSelectElement;
    await within(select).findByRole("option", { name: "РТК ИТ — Учебная среда" });
    fireEvent.change(select, { target: { value: "3" } });
    await waitFor(() => expect(api.count("PUT", "/launches/1/it-product")).toBe(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ it_product_id: 3 });
  });
});

describe("new interaction form", () => {
  it("sends the catalog IT product only when one is chosen", async () => {
    const api = mockApi({ "POST /launches": (call) => [201, { id: 9, ...(call.body as object) }] });
    renderApp("/interactions");
    fireEvent.click(await screen.findByRole("button", { name: /Новое взаимодействие/ }));
    const dialog = await screen.findByRole("dialog", { name: "Новое взаимодействие" });
    await within(dialog).findByRole("option", { name: "Технический университет" });
    await within(dialog).findByRole("option", { name: "РТК ИТ — Учебная среда" });
    const form = dialog.querySelector("form")!;
    const field = (name: string) => form.querySelector(`[name="${name}"]`) as HTMLInputElement;
    fireEvent.change(field("university_id"), { target: { value: "2" } });
    fireEvent.change(field("it_product_id"), { target: { value: "3" } });
    fireEvent.change(field("program"), { target: { value: "Python" } });
    fireEvent.change(field("product"), { target: { value: "Учебная среда" } });
    fireEvent.change(field("owner"), { target: { value: "Анна Петрова" } });
    fireEvent.change(field("deadline"), { target: { value: "2026-12-01" } });
    fireEvent.submit(form);
    await waitFor(() => expect(api.count("POST", "/launches")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({ it_product_id: 3, product: "Учебная среда" });
  });
});
