import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiRequest,
  configureApiClient,
  errorText,
  parseErrorBody,
} from "./client";

function stubFetch(status: number, body: string) {
  const fetchMock = vi.fn(async () => new Response(body, { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (e) {
    if (e instanceof ApiError) return e;
    throw e;
  }
  throw new Error("expected an ApiError");
}

describe("apiRequest", () => {
  it("returns parsed JSON and sends JSON bodies", async () => {
    const fetchMock = stubFetch(200, JSON.stringify({ id: 1, done: true }));
    await expect(apiRequest("/tasks/1", "PATCH", { done: true })).resolves.toEqual({
      id: 1,
      done: true,
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/tasks/1", {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: '{"done":true}',
    });
  });

  it("sends the CSRF token on state-changing methods only", async () => {
    configureApiClient({ csrfToken: () => "token-1" });
    const fetchMock = stubFetch(200, "{}");
    await apiRequest("/universities", "POST", { name: "x" });
    await apiRequest("/launches/1", "patch", { stage: 1 });
    await apiRequest("/auth/logout", "POST");
    await apiRequest("/tasks");
    const headers = fetchMock.mock.calls.map(
      (call) => (call as unknown as [string, RequestInit])[1].headers as Record<string, string>,
    );
    expect(headers.map((h) => h["X-CSRF-Token"])).toEqual([
      "token-1",
      "token-1",
      "token-1",
      undefined,
    ]);
  });

  it("reports 401 from data requests but not from /auth/me", async () => {
    const onUnauthenticated = vi.fn();
    configureApiClient({ onUnauthenticated });
    const body = JSON.stringify({ code: "UNAUTHENTICATED", message: "Требуется вход в систему", details: null });
    stubFetch(401, body);
    const error = await caught(apiRequest("/tasks"));
    expect(error.code).toBe("UNAUTHENTICATED");
    expect(onUnauthenticated).toHaveBeenCalledWith("/tasks");
    await caught(apiRequest("/auth/me"));
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it("parses the D-120 error shape with field details", async () => {
    stubFetch(
      422,
      JSON.stringify({
        code: "VALIDATION_ERROR",
        message: "Проверьте заполненные поля",
        details: [{ field: "name", message: "Слишком короткое", type: "string_too_short" }],
      }),
    );
    const error = await caught(apiRequest("/universities", "POST", {}));
    expect(error.status).toBe(422);
    expect(error.code).toBe("VALIDATION_ERROR");
    expect(error.message).toBe("Проверьте заполненные поля");
    expect(error.fieldMessage("name")).toBe("Слишком короткое");
    expect(errorText(error)).toBe("Проверьте заполненные поля (код VALIDATION_ERROR)");
  });

  it("falls back to the legacy FastAPI string detail", async () => {
    stubFetch(404, JSON.stringify({ detail: "Not found" }));
    const error = await caught(apiRequest("/launches/9"));
    expect(error).toMatchObject({ status: 404, code: "HTTP_404", message: "Not found", details: null });
  });

  it("maps legacy FastAPI validation lists to field details", () => {
    const error = parseErrorBody(422, {
      detail: [{ loc: ["body", "city"], msg: "Field required", type: "missing" }],
    });
    expect(error.code).toBe("HTTP_422");
    expect(error.details).toEqual([{ field: "city", message: "Field required", type: "missing" }]);
  });

  it("handles non-JSON error bodies", async () => {
    stubFetch(502, "<html>Bad Gateway</html>");
    const error = await caught(apiRequest("/tasks"));
    expect(error.code).toBe("HTTP_502");
    expect(error.message).toContain("502");
  });

  it("reports network failures as NETWORK_ERROR", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const error = await caught(apiRequest("/tasks"));
    expect(error).toMatchObject({ status: 0, code: "NETWORK_ERROR", message: "Сервер недоступен" });
    expect(errorText(error)).toBe("Сервер недоступен (код NETWORK_ERROR)");
  });
});
