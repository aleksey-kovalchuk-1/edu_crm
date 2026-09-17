import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE, apiRequest } from "./client";

/* Types of backend/app/report_routes.py (docs/api/reports.md) */

export interface ReportColumn {
  key: string;
  label: string;
}

export type ReportFormat = "xlsx" | "xls" | "pdf" | "json";
export type ReportJobStatus = "queued" | "running" | "succeeded" | "failed";

export interface ReportJob {
  id: number;
  status: ReportJobStatus;
  format: ReportFormat;
  created_at: string;
  finished_at: string | null;
}

export interface ReportRequest {
  period_from?: string;
  period_to?: string;
  university_ids?: number[];
  it_direction_ids?: number[];
  it_product_ids?: number[];
  responsible?: string[];
  status_ids?: number[];
  columns?: string[];
  format: ReportFormat;
}

export const reportDownloadUrl = (jobId: number) => `${API_BASE}/reports/${jobId}/download`;

export const FORMAT_LABELS: Record<ReportFormat, string> = {
  xlsx: "Excel (.xlsx)",
  xls: "Excel 97-2003 (.xls)",
  pdf: "PDF",
  json: "JSON",
};

export const STATUS_LABELS: Record<ReportJobStatus, string> = {
  queued: "В очереди",
  running: "Формируется",
  succeeded: "Готов",
  failed: "Ошибка",
};

const reportKeys = {
  columns: ["report-columns"] as const,
  jobs: ["report-jobs"] as const,
};

export const useReportColumns = () =>
  useQuery({
    queryKey: reportKeys.columns,
    queryFn: () => apiRequest<ReportColumn[]>("/reports/columns"),
    staleTime: Infinity,
  });

const isPending = (job: ReportJob) => job.status === "queued" || job.status === "running";

export const useReportJobs = () =>
  useQuery({
    queryKey: reportKeys.jobs,
    queryFn: () => apiRequest<ReportJob[]>("/reports"),
    // Poll only while something is still generating; otherwise a plain, one-shot fetch.
    refetchInterval: (query) => (query.state.data?.some(isPending) ? 1500 : false),
  });

export function useCreateReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: ReportRequest) => apiRequest<ReportJob>("/reports", "POST", data),
    onSuccess: () => void client.invalidateQueries({ queryKey: reportKeys.jobs }),
  });
}
