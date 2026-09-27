import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";

/* Types of backend/app/security_routes.py */

export interface SessionItem { id: string; device: string; ip: string | null; created_at: string; last_active_at: string; current: boolean; }
export interface LoginHistory {
  crm: { at: string; device: string; ip: string | null; state: "active" | "ended" | "expired" }[];
  keycloak: { available: boolean; reason: string | null; events: { at: string; type: string; label: string; ip: string | null; error: string | null }[] };
}
export interface PasswordPolicy { available: boolean; rules: string[]; brute_force: string | null; change_password_url: string; admin_console_url: string | null; }

const keys = { sessions: ["security", "sessions"] as const, history: ["security", "history"] as const, policy: ["security", "policy"] as const };

export const useSessions = () => useQuery({ queryKey: keys.sessions, queryFn: () => apiRequest<SessionItem[]>("/security/sessions") });
export const useLoginHistory = () => useQuery({ queryKey: keys.history, queryFn: () => apiRequest<LoginHistory>("/security/login-history") });
export const usePasswordPolicy = () => useQuery({ queryKey: keys.policy, queryFn: () => apiRequest<PasswordPolicy>("/security/password-policy") });

function useSessionMutation<T>(fn: (vars: T) => Promise<{ message: string }>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => { void client.invalidateQueries({ queryKey: ["security"] }); } });
}
export const useTerminateSession = () =>
  useSessionMutation((id: string) => apiRequest<{ message: string }>(`/security/sessions/${id}`, "DELETE"));
export const useTerminateOthers = () =>
  useSessionMutation(() => apiRequest<{ message: string }>("/security/sessions/terminate-others", "POST"));
