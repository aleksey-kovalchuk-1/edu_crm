import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { ApiError, apiRequest } from "./client";
import { catalogKeys } from "./catalogs";
import { invalidateAudit, queryKeys } from "./queries";
import type { PersonRef } from "./types";

/* Types of docs/api/imports.md (T-033) */

/** CRM field name → file header, or null when the field is not loaded. */
export type ImportMapping = Record<string, string | null>;

export interface ImportField {
  name: string;
  label: string;
  required: boolean;
}

export interface ImportPreviewRow {
  row_number: number;
  /** Cells in the order of `headers`; dates are YYYY-MM-DD, empty cells null. */
  cells: (string | number | boolean | null)[];
}

export type ImportStatus = "uploaded" | "applied";
export type ImportRowStatus = "ok" | "warning" | "error" | "skipped";
export type ImportRowAction = "create" | "update" | null;

export interface ImportSummary {
  rows: number;
  valid: number;
  invalid: number;
  skipped: number;
  with_warnings: number;
  /** Entity → count, e.g. {contracts: 110, universities: 3}. */
  created: Record<string, number>;
  updated: Record<string, number>;
}

export interface ImportRowResult {
  row_number: number;
  status: ImportRowStatus;
  action: ImportRowAction;
  contract_number: string | null;
  errors: string[];
  warnings: string[];
}

export interface ImportReport {
  summary: ImportSummary;
  rows: ImportRowResult[];
}

export interface ImportUpload {
  id: number;
  filename: string;
  status: ImportStatus;
  header_row: number;
  headers: string[];
  mapping: ImportMapping;
  row_count: number;
  /** May be absent in GET /imports/{id}. */
  preview?: ImportPreviewRow[] | null;
  created_at: string;
  created_by: PersonRef | null;
  applied_at?: string | null;
  report: ImportReport | null;
}

export interface ImportListItem {
  id: number;
  filename: string;
  status: ImportStatus;
  row_count: number;
  created_at: string;
  created_by: PersonRef | null;
  applied_at: string | null;
  summary: ImportSummary | null;
}

/* Client-side file checks (the server checks again by content) */

export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
export const IMPORT_ACCEPT =
  ".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export const formatFileSize = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} КБ`
    : `${(bytes / 1024 / 1024).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} МБ`;

/** Russian message when the file cannot be uploaded, otherwise null. */
export function importFileProblem(file: File): string | null {
  if (!/\.xlsx?$/i.test(file.name)) {
    return `Файл «${file.name}» не подходит: выберите таблицу Excel в формате .xls или .xlsx.`;
  }
  if (file.size > MAX_IMPORT_BYTES) {
    return `Файл «${file.name}» весит ${formatFileSize(file.size)} — это больше допустимых 10 МБ. Разделите таблицу на части.`;
  }
  if (file.size === 0) return `Файл «${file.name}» пустой.`;
  return null;
}

/** True for a 422 about the mapping (not chosen, missing column, one column for two fields). */
export const isMappingError = (error: unknown): error is ApiError =>
  error instanceof ApiError &&
  error.status === 422 &&
  !!error.details?.some((d) => d.field === "mapping" || !!d.field?.startsWith("mapping."));

/* Queries */

export const importKeys = {
  fields: ["import-fields"] as const,
  all: ["imports"] as const,
  list: ["imports", "list"] as const,
  detail: (id: number) => ["imports", "detail", id] as const,
};

export const useImportFields = () =>
  useQuery({
    queryKey: importKeys.fields,
    queryFn: () => apiRequest<ImportField[]>("/imports/fields"),
    staleTime: Infinity,
  });

export const useImports = () =>
  useQuery({
    queryKey: importKeys.list,
    queryFn: () => apiRequest<ImportListItem[]>("/imports"),
  });

export const useImport = (id: number) =>
  useQuery({
    queryKey: importKeys.detail(id),
    queryFn: () => apiRequest<ImportUpload>(`/imports/${id}`),
  });

const invalidateImports = (client: QueryClient) =>
  void client.invalidateQueries({ queryKey: importKeys.all });

/** Data an applied import may change; refreshed in the background. */
export function invalidateAfterApply(client: QueryClient) {
  for (const queryKey of [
    catalogKeys.contracts,
    catalogKeys.universities,
    catalogKeys.products,
    catalogKeys.directions,
    ["university-contacts"],
    queryKeys.dashboard,
  ]) {
    void client.invalidateQueries({ queryKey });
  }
  invalidateAudit(client);
  invalidateImports(client);
}

export function useUploadImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file, file.name);
      return apiRequest<ImportUpload>("/imports", "POST", form);
    },
    onSuccess: () => invalidateImports(client),
  });
}

export interface MappingRequest {
  id: number;
  mapping: ImportMapping;
}

export const useCheckImport = () =>
  useMutation({
    mutationFn: ({ id, mapping }: MappingRequest) =>
      apiRequest<ImportReport>(`/imports/${id}/check`, "POST", { mapping }),
  });

export function useApplyImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, mapping }: MappingRequest) =>
      apiRequest<ImportReport>(`/imports/${id}/apply`, "POST", { mapping }),
    onSuccess: () => invalidateAfterApply(client),
    onError: (error) => {
      // Already applied elsewhere: the history shows the new status.
      if (error instanceof ApiError && error.status === 409) invalidateImports(client);
    },
  });
}
