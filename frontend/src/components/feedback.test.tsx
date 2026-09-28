import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorSummary } from "./ErrorSummary";
import { Notice } from "./Notice";
import { SettingsPanel } from "../pages/settings/SettingsPanel";

describe("Notice", () => {
  it("announces errors and warnings as alerts and the rest as status, with a text tone class", () => {
    render(<><Notice tone="error">Сбой</Notice><Notice tone="warning">Внимание</Notice><Notice tone="success">Готово</Notice><Notice tone="info">Сведения</Notice></>);
    expect(screen.getAllByRole("alert").map((n) => n.textContent)).toEqual(["Сбой", "Внимание"]);
    expect(screen.getAllByRole("status").map((n) => n.textContent)).toEqual(["Готово", "Сведения"]);
    expect(screen.getByText("Готово").closest(".notice")?.className).toContain("notice-success");
  });

  it("lets a caller keep an existing role", () => {
    render(<Notice tone="error" role="status">Запуск завершился ошибкой</Notice>);
    expect(screen.getByRole("status").textContent).toBe("Запуск завершился ошибкой");
  });
});

describe("ErrorSummary", () => {
  it("renders nothing without errors", () => {
    const { container } = render(<ErrorSummary errors={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("takes focus, counts the errors and moves focus to a field from its link", () => {
    render(
      <>
        <input id="f-name" aria-label="Имя" />
        <ErrorSummary errors={[{ id: "f-name", label: "Имя", message: "Укажите имя" }, { id: "f-phone", label: "Телефон", message: "Неверный номер" }]} />
      </>,
    );
    const summary = screen.getByRole("group", { name: /Исправьте 2 поля/ });
    expect(document.activeElement).toBe(summary);
    fireEvent.click(screen.getByRole("link", { name: "Имя: Укажите имя" }));
    expect(document.activeElement?.id).toBe("f-name");
  });
});

describe("SettingsPanel", () => {
  it("renders a labelled section with heading, description and body", () => {
    render(<SettingsPanel titleId="t" title="Пауза" description="Пока пауза действует…">тело</SettingsPanel>);
    const region = screen.getByRole("region", { name: "Пауза" });
    expect(region.textContent).toContain("Пока пауза действует…");
    expect(region.querySelector(".settings-body")?.textContent).toBe("тело");
  });

  it("renders a form when given onSubmit", () => {
    render(<SettingsPanel titleId="t2" title="Личные данные" onSubmit={(e) => e.preventDefault()}>поля</SettingsPanel>);
    expect(screen.getByRole("form", { name: "Личные данные" })).toBeTruthy();
  });
});
