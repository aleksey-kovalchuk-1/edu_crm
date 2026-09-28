import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryFallback } from "./QueryState";

const query = (over: Partial<Parameters<typeof queryFallback>[0][number]> = {}) => ({
  isPending: false, isError: false, data: undefined, error: null, refetch: async () => undefined, ...over,
});

describe("queryFallback", () => {
  it("announces loading as a polite status", () => {
    render(<>{queryFallback([query({ isPending: true })])}</>);
    expect(screen.getByRole("status").textContent).toMatch(/Загружаем/);
  });

  it("shows the error with a retry button and a next step", () => {
    render(<>{queryFallback([query({ isError: true, error: new Error("boom") })])}</>);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Повторить/ })).toBeTruthy();
  });
});
