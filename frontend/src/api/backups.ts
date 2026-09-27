import { useQuery } from "@tanstack/react-query";
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
