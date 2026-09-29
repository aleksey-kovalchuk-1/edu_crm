import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";

/* Types of backend/app/admin_routes.py (Настройки → Пользователи и роли / Аккаунт) */

export interface AdminUser {
  keycloak_id: string;
  username: string;
  email: string;
  full_name: string;
  roles: string[];
  is_active: boolean;
  last_login_at: string | null;
  /** Hasn't confirmed the address or set a password yet (Keycloak still asks for it). */
  setup_pending: boolean;
}

export interface AdminUsers {
  available: boolean;
  total: number;
  users: AdminUser[];
}

export interface NewAccount {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: "crm-user" | "crm-admin";
}

export interface CreatedAccount {
  keycloak_id: string;
  username: string;
  email: string;
  role: string;
  temporary_password: string;
}

export type AssignableRole = "crm-user" | "crm-admin";

export interface ChangedRole {
  keycloak_id: string;
  username: string;
  role: AssignableRole;
  /** Granting a first role to someone without a password e-mails them a setup link. */
  password_setup: "sent" | "not_needed" | "failed";
}

export interface SetupEmailResult {
  sent: boolean;
  message: string;
}

export interface ResetPasswordResult {
  keycloak_id: string;
  username: string;
  temporary_password: string;
}

export interface PendingRegistration {
  keycloak_id: string;
  email: string;
  username: string;
}

export interface PendingRegistrations {
  available: boolean;
  pending: PendingRegistration[];
}

export const adminKeys = {
  users: ["admin", "users"] as const,
  pending: ["admin", "pending-registrations"] as const,
};

/** GET /admin/users — superadmin only. */
export const useAdminUsers = () =>
  useQuery({
    queryKey: adminKeys.users,
    queryFn: () => apiRequest<AdminUsers>("/admin/users"),
  });

/** POST /admin/users — only Irina's superadmin role can create managers and administrators. */
export function useCreateAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: NewAccount) => apiRequest<CreatedAccount>("/admin/users", "POST", data),
    onSuccess: () => { void client.invalidateQueries({ queryKey: adminKeys.users }); },
  });
}

/** PATCH /admin/users/{id}/role — manager or administrator; privileged roles are protected. */
export function useChangeUserRole() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ keycloakId, role }: { keycloakId: string; role: AssignableRole }) =>
      apiRequest<ChangedRole>(`/admin/users/${keycloakId}/role`, "PATCH", { role }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: adminKeys.users });
      void client.invalidateQueries({ queryKey: adminKeys.pending });
    },
  });
}

/** DELETE /admin/users/{id}/role — ends CRM access; the person reappears in «Заявки на доступ». */
export function useRemoveUserRole() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ keycloakId }: { keycloakId: string; username: string }) =>
      apiRequest<void>(`/admin/users/${keycloakId}/role`, "DELETE"),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: adminKeys.users });
      void client.invalidateQueries({ queryKey: adminKeys.pending });
    },
  });
}

/** POST /admin/users/{id}/password-setup-email — Keycloak's «confirm the address and set a password» link, 12 hours. */
export function useSendPasswordSetup() {
  return useMutation({
    mutationFn: (keycloakId: string) =>
      apiRequest<SetupEmailResult>(`/admin/users/${keycloakId}/password-setup-email`, "POST"),
  });
}

/** POST /admin/users/{id}/reset-password — the temporary password is returned only once. */
export function useResetUserPassword() {
  return useMutation({
    mutationFn: (keycloakId: string) =>
      apiRequest<ResetPasswordResult>(`/admin/users/${keycloakId}/reset-password`, "POST"),
  });
}

/** GET /admin/pending-registrations — superadmin only. */
export const usePendingRegistrations = () =>
  useQuery({
    queryKey: adminKeys.pending,
    queryFn: () => apiRequest<PendingRegistrations>("/admin/pending-registrations"),
  });

/** POST /admin/pending-registrations/{id}/approve — grants the baseline crm-user role. */
export function useApprovePendingRegistration() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (keycloakId: string) =>
      apiRequest<void>(`/admin/pending-registrations/${keycloakId}/approve`, "POST"),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: adminKeys.pending });
      void client.invalidateQueries({ queryKey: adminKeys.users });
    },
  });
}
