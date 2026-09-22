import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";

/* Types of backend/app/admin_routes.py (Настройки → Пользователи и роли / Аккаунт) */

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  roles: string[];
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUsers {
  total: number;
  users: AdminUser[];
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
