export interface University {
  id: number;
  name: string;
  city: string;
  contact: string;
}
export interface Launch {
  id: number;
  university_id: number;
  university: string;
  city: string;
  program: string;
  product: string;
  owner: string;
  students: number;
  stage: number;
  deadline: string;
  overdue: boolean;
}
export interface Task {
  id: number;
  launch_id: number;
  title: string;
  owner: string;
  deadline: string;
  done: boolean;
}
export interface StageEvent {
  id: number;
  stage: number;
  created_at: string;
}
export interface Dashboard {
  universities: number;
  launches: number;
  students: number;
  overdue: number;
  annual: {
    year: number;
    applications: number;
    students: number;
    streams: number;
  }[];
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: data ? { "Content-Type": "application/json" } : undefined,
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Не удалось выполнить запрос (${response.status}). Проверьте заполненные поля.`,
    );
  }
  return response.json();
}
