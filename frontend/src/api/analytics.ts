import { useQuery } from "@tanstack/react-query";
import { API_BASE, apiRequest } from "./client";

export interface AnalyticsParams {
  period_from: string;
  period_to: string;
  time_zone: string;
  university_id: number[];
}

export interface AnalyticsSnapshot {
  period_from: string;
  period_to: string;
  time_zone: string;
  universities: string[];
  stages: { name: string; count: number }[];
  monthly: { month: string; count: number }[];
  ranking: { id: number; name: string; programs: number; students: number }[];
  has_stage_data: boolean;
  has_implementation_data: boolean;
}

export function analyticsQuery(params: AnalyticsParams): string {
  const search = new URLSearchParams({
    period_from: params.period_from,
    period_to: params.period_to,
    time_zone: params.time_zone,
  });
  params.university_id.forEach((id) => search.append("university_id", String(id)));
  return `?${search.toString()}`;
}

export const analyticsPdfUrl = (params: AnalyticsParams) =>
  `${API_BASE}/analytics/interactions.pdf${analyticsQuery(params)}`;

export function useInteractionAnalytics(params: AnalyticsParams, enabled: boolean) {
  return useQuery({
    queryKey: ["analytics", params.period_from, params.period_to, params.time_zone, ...params.university_id],
    queryFn: () => apiRequest<AnalyticsSnapshot>(`/analytics/interactions${analyticsQuery(params)}`),
    enabled,
  });
}
