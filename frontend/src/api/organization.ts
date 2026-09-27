import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiRequest } from "./client";

/* Types of backend/app/organization_routes.py */

export interface Organization {
  name: string;
  legal_name: string;
  ogrn: string;
  registration_date: string;
  legal_address: string;
  postal_address: string;
  contact_address: string;
  phone: string;
  phone_display: string;
  email: string;
  updated_at: string | null;
}

export type OrganizationInput = Omit<Organization, "phone_display" | "updated_at">;

export const organizationKeys = {
  card: ["organization"] as const,
  brand: ["organization", "brand"] as const,
};

export const useOrganization = () =>
  useQuery({ queryKey: organizationKeys.card, queryFn: () => apiRequest<Organization>("/organization") });

/** Public: the name for the sidebar and the login screen. A failure just hides the name line. */
export const useBrand = () =>
  useQuery({
    queryKey: organizationKeys.brand,
    queryFn: () => apiRequest<{ name: string }>("/organization/brand"),
    staleTime: 5 * 60 * 1000,
    retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
  });

export function useUpdateOrganization() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: OrganizationInput) => apiRequest<Organization>("/organization", "PUT", data),
    onSuccess: (organization) => {
      client.setQueryData(organizationKeys.card, organization);
      client.setQueryData(organizationKeys.brand, { name: organization.name });
    },
  });
}
