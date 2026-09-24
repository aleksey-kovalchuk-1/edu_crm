import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { apiRequest } from "./client";
import type {
  AuditEvent,
  Dashboard,
  Launch,
  LaunchInput,
} from "./types";

/** Stable query keys; one per endpoint. Tasks keys live in api/tasks.ts (they carry list params). */
export const queryKeys = {
  launches: ["launches"] as const,
  stages: ["stages"] as const,
  dashboard: ["dashboard"] as const,
  audit: ["audit"] as const,
  auditRecent: (limit: number) => ["audit", "recent", limit] as const,
};

export const useRecentActions = (limit = 10) =>
  useQuery({
    queryKey: queryKeys.auditRecent(limit),
    queryFn: () => apiRequest<AuditEvent[]>(`/audit/recent?limit=${limit}`),
  });

/** Every successful change adds an audit event; refresh any recent-actions list in the background. */
export const invalidateAudit = (client: QueryClient) =>
  void client.invalidateQueries({ queryKey: queryKeys.audit });

export const useLaunches = () =>
  useQuery({
    queryKey: queryKeys.launches,
    queryFn: () => apiRequest<Launch[]>("/launches"),
  });

export const useStages = () =>
  useQuery({
    queryKey: queryKeys.stages,
    queryFn: () => apiRequest<string[]>("/stages"),
    staleTime: Infinity,
  });

export const useDashboard = () =>
  useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => apiRequest<Dashboard>("/dashboard"),
  });

/**
 * Mark queries stale and refetch the active ones in the background. Not
 * awaited, so a mutation stops being pending as soon as the server answers.
 */
export const invalidate = (client: QueryClient, ...keys: (readonly unknown[])[]) => {
  for (const queryKey of keys)
    void client.invalidateQueries({ queryKey, exact: true });
};

/** Links an interaction to a catalog IT product (or clears the link with null). */
export function useSetLaunchProduct(launchId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (it_product_id: number | null) =>
      apiRequest<Launch>(`/launches/${launchId}/it-product`, "PUT", { it_product_id }),
    onSuccess: () => {
      invalidate(client, queryKeys.launches);
      invalidateAudit(client);
    },
  });
}

export function useCreateLaunch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: LaunchInput) =>
      apiRequest<Launch>("/launches", "POST", data),
    onSuccess: () => {
      invalidate(client, queryKeys.launches, queryKeys.dashboard);
      invalidateAudit(client);
    },
  });
}
