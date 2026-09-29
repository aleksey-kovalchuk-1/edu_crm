import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Launch } from "../api/types";
import { mockApi, renderApp } from "../test/utils";

const launch = (id: number, extra: Partial<Launch>): Launch => ({
  id, university_id: 1, university: "Колледж связи", city: "Казань", program: "Python", product: "Учебная среда",
  owner: "Анна Демо", students: 10, stage: 0, deadline: "2026-12-01", overdue: false, workflow_template_id: 1,
  status_id: 11, it_product_id: 3, ...extra,
});
const LAUNCHES = [
  launch(1, {}),
  launch(2, { university_id: 2, university: "Технический университет", program: "DevOps", status_id: 12 }),
  launch(3, { program: "DevOps", it_product_id: null, product: "Облачная лаборатория", status_id: 14 }),
];
const shown = () => [...document.querySelectorAll(".launch-code")].map((code) => code.textContent);

async function open(path = "/interactions") {
  mockApi({ "GET /launches": () => LAUNCHES });
  renderApp(path);
  return screen.findByRole("group", { name: "Фильтры взаимодействий" });
}

describe("interactions register: filters", () => {
  it("offers university, programme, IT product and status filters", async () => {
    const filters = await open();
    for (const label of ["Вуз", "ИТ-программа", "ИТ-продукт", "Статус"]) {
      expect(within(filters).getByLabelText(label)).toBeTruthy();
    }
    const status = within(filters).getByLabelText("Статус") as HTMLSelectElement;
    expect([...status.options].map((o) => o.textContent)).toEqual(["Все статусы", "Первый контакт", "Согласование документов", "Сопровождение"]);
  });

  it("combines the filters and shows how many remain", async () => {
    const filters = await open();
    expect(shown()).toEqual(["ВЗ-0001", "ВЗ-0002", "ВЗ-0003"]);
    fireEvent.change(within(filters).getByLabelText("ИТ-программа"), { target: { value: "DevOps" } });
    expect(shown()).toEqual(["ВЗ-0002", "ВЗ-0003"]);
    fireEvent.change(within(filters).getByLabelText("Вуз"), { target: { value: "1" } });
    expect(shown()).toEqual(["ВЗ-0003"]);
    fireEvent.change(within(filters).getByLabelText("Вуз"), { target: { value: "" } });
    fireEvent.change(within(filters).getByLabelText("Статус"), { target: { value: "12" } });
    expect(shown()).toEqual(["ВЗ-0002"]);
    fireEvent.click(within(filters).getByRole("button", { name: "Сбросить фильтры" }));
    expect(shown()).toEqual(["ВЗ-0001", "ВЗ-0002", "ВЗ-0003"]);
  });

  it("filters by catalog IT product", async () => {
    const filters = await open();
    const product = within(filters).getByLabelText("ИТ-продукт") as HTMLSelectElement;
    expect([...product.options].map((o) => o.textContent)).toContain("РТК ИТ — Учебная среда");
    fireEvent.change(product, { target: { value: "3" } });
    expect(shown()).toEqual(["ВЗ-0001", "ВЗ-0002"]);
  });

  it("keeps the filters in the address so a view can be shared", async () => {
    await open("/interactions?university=2&status=12");
    expect(shown()).toEqual(["ВЗ-0002"]);
    expect((screen.getByLabelText("Вуз") as HTMLSelectElement).value).toBe("2");
  });

  it("also finds interactions by their product in the search", async () => {
    await open();
    fireEvent.change(screen.getByLabelText("Поиск"), { target: { value: "Облачная" } });
    expect(shown()).toEqual(["ВЗ-0003"]);
  });
});
