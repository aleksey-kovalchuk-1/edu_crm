import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { invalidateAudit } from "./queries";

export type AlertStatus = "open" | "in_review" | "cleared" | "confirmed";
export type AlertPriority = "low" | "medium" | "high";
export type ResolutionCode = "legitimate_shared_contact" | "data_corrected" | "false_positive" |
  "confirmed_by_review" | "needs_more_information";
export interface FraudAlert {
  id: number; rule_code: string; rule_version: number; evidence_kind: string | null;
  priority: AlertPriority; status: AlertStatus; entity_type: string | null; entity_id: number | null;
  related_entity_id: number | null; batch_id: number | null; row_number: number | null;
  created_at: string; updated_at: string; reviewed_by_user_id: number | null;
  reviewed_at: string | null; resolution_code: ResolutionCode | null;
}
export interface FraudStatus { document_match: "disabled_no_key" | "needs_backfill" | "active";
  rule_version: number; batch_row_limit: number; hourly_import_limit: number }

const alertKeys = ["fraud-alerts"] as const;
export const useFraudStatus = () => useQuery({ queryKey: [...alertKeys, "status"],
  queryFn: () => apiRequest<FraudStatus>("/fraud-alerts/status") });
export const useFraudAlerts = (status = "", priority = "") => useQuery({
  queryKey: [...alertKeys, "list", status, priority],
  queryFn: () => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (priority) params.set("priority", priority);
    const suffix = params.size ? `?${params.toString()}` : "";
    return apiRequest<FraudAlert[]>(`/fraud-alerts${suffix}`);
  },
});
export const useFraudAlert = (id: number | null) => useQuery({
  queryKey: [...alertKeys, "detail", id],
  queryFn: () => apiRequest<FraudAlert>(`/fraud-alerts/${id}`), enabled: id !== null,
});
export function useReviewFraudAlert() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, resolution_code, expected_updated_at }: {
      id: number; status: AlertStatus; resolution_code: ResolutionCode | null; expected_updated_at: string;
    }) => apiRequest<FraudAlert>(`/fraud-alerts/${id}`, "PATCH", { status, resolution_code, expected_updated_at }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: alertKeys }); invalidateAudit(client); },
  });
}
