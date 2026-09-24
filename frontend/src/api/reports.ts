import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { API_BASE, apiRequest } from "./client";

/* Types of backend/app/report_routes.py (D-221) */

export interface ReportColumn {
  key: string;
  label: string;
}

export interface ReportOptions {
  owners: string[];
  statuses: { id: number; name: string; workflow: string }[];
  columns: (ReportColumn & { default: boolean })[];
}

export type ReportRow = Record<string, string | number>;

export interface ReportPreview {
  columns: ReportColumn[];
  rows: ReportRow[];
  total: number;
}

export interface ReportParams {
  period_from?: string;
  period_to?: string;
  university_id: number[];
  it_direction_id: number[];
  it_product_id: number[];
  owner: string[];
  status_id: number[];
  column: string[];
}

export type ReportFormat = "xlsx" | "xls" | "pdf";

/** Query string shared by the preview and the downloads, so the file always matches the screen. */
export function reportQuery(params: ReportParams): string {
  const q = new URLSearchParams();
  if (params.period_from) q.set("period_from", params.period_from);
  if (params.period_to) q.set("period_to", params.period_to);
  for (const key of ["university_id", "it_direction_id", "it_product_id", "owner", "status_id", "column"] as const) {
    for (const value of params[key]) q.append(key, String(value));
  }
  return q.toString();
}

export const reportExportUrl = (params: ReportParams, format: ReportFormat) => {
  const qs = reportQuery(params);
  return `${API_BASE}/reports/interactions/export?format=${format}${qs ? `&${qs}` : ""}`;
};

export const useReportOptions = () =>
  useQuery({
    queryKey: ["reports", "options"] as const,
    queryFn: () => apiRequest<ReportOptions>("/reports/options"),
  });

export const useReportPreview = (params: ReportParams, enabled: boolean) =>
  useQuery({
    queryKey: ["reports", "preview", reportQuery(params)] as const,
    queryFn: () => apiRequest<ReportPreview>(`/reports/interactions?${reportQuery(params)}`),
    enabled,
    placeholderData: keepPreviousData,
  });
