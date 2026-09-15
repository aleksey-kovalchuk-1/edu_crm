/** One entry of the `details` list of an API error (D-120). */
export interface ErrorDetail {
  field: string | null;
  message: string;
  type: string | null;
}

/** Error thrown by {@link apiRequest}; `status` is 0 when the server was not reached. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[] | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: ErrorDetail[] | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Message for a given form field, if the server reported one. */
  fieldMessage(field: string): string | undefined {
    return this.details?.find((d) => d.field === field)?.message;
  }
}

export const API_BASE = "/api/v1";

const LOCATION_PREFIXES = new Set(["body", "query", "path", "header", "cookie"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function defaultMessage(status: number): string {
  if (status === 422) return "Проверьте заполненные поля";
  return `Не удалось выполнить запрос (${status})`;
}

/** Legacy FastAPI validation list: [{loc, msg, type}] → details. */
function legacyDetails(list: unknown[]): ErrorDetail[] {
  return list.filter(isRecord).map((item) => {
    const loc = Array.isArray(item.loc) ? item.loc.map(String) : [];
    if (loc.length && LOCATION_PREFIXES.has(loc[0])) loc.shift();
    return {
      field: loc.length ? loc.join(".") : null,
      message: typeof item.msg === "string" ? item.msg : "",
      type: typeof item.type === "string" ? item.type : null,
    };
  });
}

/** Build an ApiError from a non-OK response body of either supported shape. */
export function parseErrorBody(status: number, body: unknown): ApiError {
  const fallbackCode = `HTTP_${status}`;
  if (isRecord(body)) {
    if (typeof body.code === "string" && typeof body.message === "string") {
      const details = Array.isArray(body.details)
        ? body.details.filter(isRecord).map((d) => ({
            field: typeof d.field === "string" ? d.field : null,
            message: typeof d.message === "string" ? d.message : "",
            type: typeof d.type === "string" ? d.type : null,
          }))
        : null;
      return new ApiError(status, body.code, body.message, details);
    }
    if (typeof body.detail === "string") {
      return new ApiError(status, fallbackCode, body.detail);
    }
    if (Array.isArray(body.detail)) {
      return new ApiError(
        status,
        fallbackCode,
        defaultMessage(status),
        legacyDetails(body.detail),
      );
    }
  }
  return new ApiError(status, fallbackCode, defaultMessage(status));
}

export async function apiRequest<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers:
        data !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Сервер недоступен");
  }
  const text = await response.text().catch(() => "");
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) throw parseErrorBody(response.status, body);
  if (text && body === null && text.trim() !== "null") {
    throw new ApiError(
      response.status,
      "INVALID_RESPONSE",
      "Сервер вернул некорректный ответ",
    );
  }
  return body as T;
}

/** Text shown to users for any error: "<message> (код <code>)". */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (код ${error.code})`;
  if (error instanceof Error) return `${error.message} (код CLIENT_ERROR)`;
  return "Неизвестная ошибка (код CLIENT_ERROR)";
}
