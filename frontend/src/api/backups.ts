import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";

/* Types of backend/app/backup_routes.py */

export interface BackupFile { file: string; size_bytes: number; created_at: string; }
export interface BackupPair { label: string; database: BackupFile | null; attachments: BackupFile | null; }
export interface BackupRun {
  trigger: "scheduled" | "manual";
  label: string;
  started_at: string;
  finished_at: string | null;
  result: "running" | "success" | "failure" | "interrupted";
  verified: boolean | null;
  error: string | null;
}
export interface BackupStatus {
  available: boolean;
  reason: "not_configured" | "no_report" | "damaged" | null;
  last_run: BackupRun | null;
  last_success_at: string | null;
  stale: boolean;
  pairs: BackupPair[];
  retention: { days: number; min_pairs: number; verification_configured: boolean } | null;
  pending_request: boolean;
}

const statusKey = ["backups", "status"] as const;

/** Polls every 10 s while a manual copy is waiting or a backup is running, so the page follows it. */
export const useBackupStatus = (enabled: boolean) =>
  useQuery({
    queryKey: statusKey,
    queryFn: () => apiRequest<BackupStatus>("/backups/status"),
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && (data.pending_request || data.last_run?.result === "running") ? 10_000 : false;
    },
  });

export function useRequestBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest<{ state: string }>("/backups/manual", "POST"),
    onSuccess: () => { void client.invalidateQueries({ queryKey: statusKey }); },
  });
}
