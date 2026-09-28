import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";

export interface BackupItem {
  created_at: string;
  source: string;
  database_bytes: number;
  attachments_bytes: number;
  verified: boolean;
}

export interface BackupStatus {
  available: boolean;
  reason: "not_configured" | "missing" | "unavailable" | null;
  generated_at: string | null;
  backups: BackupItem[];
}

export const useBackupStatus = () => useQuery({
  queryKey: ["admin", "backups"],
  queryFn: () => apiRequest<BackupStatus>("/admin/backups"),
});

/* Latest run and manual request (GET /admin/backups/run, POST /admin/backups/manual). */

export interface LastBackupRun {
  trigger: "scheduled" | "manual";
  label: string;
  started_at: string;
  finished_at: string | null;
  result: "running" | "success" | "failure" | "interrupted";
  error: string | null;
}

export interface BackupRunStatus {
  available: boolean;
  reason: "not_configured" | "unavailable" | null;
  last_run: LastBackupRun | null;
  pending_request: boolean;
  pending_since: string | null;
  manual_available: boolean;
}

/** No new pair for this long means the daily backup is not running. `newest` null: no pair at all. */
export const STALE_MS = 36 * 3600_000;
export const isStale = (newest: string | null) => newest === null || Date.now() - new Date(newest).getTime() > STALE_MS;

/** A request the host agent has not picked up within this time means the agent is not responding. */
export const REQUEST_TIMEOUT_MS = 5 * 60_000;
export const isStuck = (run: BackupRunStatus) =>
  run.pending_request && run.pending_since !== null && Date.now() - new Date(run.pending_since).getTime() > REQUEST_TIMEOUT_MS;

/** Polls every 10 s while a request waits or a backup runs; stops for a request nobody picked up. */
export const useBackupRun = () => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["admin", "backups", "run"],
    queryFn: async () => {
      const run = await apiRequest<BackupRunStatus>("/admin/backups/run");
      if (!run.pending_request && run.last_run?.result !== "running") {
        void client.invalidateQueries({ queryKey: ["admin", "backups"], exact: true });  // a finished run may add a pair
      }
      return run;
    },
    refetchInterval: (query) => {
      const run = query.state.data;
      if (!run || isStuck(run)) return false;
      return run.pending_request || run.last_run?.result === "running" ? 10_000 : false;
    },
  });
};

export function useRequestBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest<{ state: string }>("/admin/backups/manual", "POST"),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["admin", "backups", "run"] }); },
  });
}
