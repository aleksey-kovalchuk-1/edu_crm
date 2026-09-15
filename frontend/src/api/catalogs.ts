import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { apiRequest } from "./client";
import { invalidateAudit, queryKeys } from "./queries";
import type {
  Contract,
  ContractFilters,
  ContractInput,
  CrmUser,
  ITDirection,
  ITDirectionInput,
  ITProduct,
  ITProductInput,
  Page,
  TransferStatus,
  University,
  UniversityContact,
  UniversityContactInput,
  UniversityInput,
} from "./types";

type QueryValue = string | number | boolean | null | undefined;

/**
 * Query string from params in their insertion order; empty strings, null,
 * undefined and false are omitted. Returns "" or "?a=1&b=2".
 */
export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false)
      continue;
    search.append(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export interface ListParams {
  q?: string;
  include_inactive?: boolean;
}
export interface ProductListParams extends ListParams {
  direction_id?: number;
}

/** Default page size of paginated lists. */
export const PAGE_SIZE = 50;

/** Query keys; list keys include their filters, roots allow prefix invalidation. */
export const catalogKeys = {
  directions: ["it-directions"] as const,
  directionList: (p: ListParams) => ["it-directions", p] as const,
  products: ["it-products"] as const,
  productList: (p: ProductListParams) => ["it-products", p] as const,
  universities: ["universities"] as const,
  universityList: (p: ListParams) => ["universities", p] as const,
  users: (role: string) => ["users", role] as const,
  contacts: (universityId: number) => ["university-contacts", universityId] as const,
  contactList: (universityId: number, p: ListParams) =>
    ["university-contacts", universityId, p] as const,
  contracts: ["contracts"] as const,
  contractList: (f: ContractFilters) => ["contracts", f] as const,
  transferStatuses: ["contract-transfer-statuses"] as const,
};

/** Prefix invalidation: every list of that entity, whatever its filters. */
const invalidatePrefix = (client: QueryClient, ...keys: (readonly unknown[])[]) => {
  for (const queryKey of keys) void client.invalidateQueries({ queryKey });
};

const listQuery = (p: ListParams) =>
  buildQuery({ q: p.q?.trim(), include_inactive: p.include_inactive });

/* ИТ-направления */

export const useItDirections = (params: ListParams = {}) =>
  useQuery({
    queryKey: catalogKeys.directionList(params),
    queryFn: () => apiRequest<ITDirection[]>(`/it-directions${listQuery(params)}`),
    placeholderData: keepPreviousData,
  });

export function useSaveItDirection() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: ITDirectionInput }) =>
      id === undefined
        ? apiRequest<ITDirection>("/it-directions", "POST", data)
        : apiRequest<ITDirection>(`/it-directions/${id}`, "PATCH", data),
    onSuccess: () => {
      // Products embed direction names.
      invalidatePrefix(client, catalogKeys.directions, catalogKeys.products);
      invalidateAudit(client);
    },
  });
}

/* ИТ-продукты */

export const useItProducts = (params: ProductListParams = {}) =>
  useQuery({
    queryKey: catalogKeys.productList(params),
    queryFn: () =>
      apiRequest<ITProduct[]>(
        `/it-products${buildQuery({
          q: params.q?.trim(),
          direction_id: params.direction_id,
          include_inactive: params.include_inactive,
        })}`,
      ),
    placeholderData: keepPreviousData,
  });

export function useSaveItProduct() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: ITProductInput }) =>
      id === undefined
        ? apiRequest<ITProduct>("/it-products", "POST", data)
        : apiRequest<ITProduct>(`/it-products/${id}`, "PATCH", data),
    onSuccess: (_data, { id }) => {
      invalidatePrefix(client, catalogKeys.products);
      // Contracts show vendor and product name.
      if (id !== undefined) invalidatePrefix(client, catalogKeys.contracts);
      invalidateAudit(client);
    },
  });
}

/* Учебные заведения */

export const useUniversities = (params: ListParams = {}) =>
  useQuery({
    queryKey: catalogKeys.universityList(params),
    queryFn: () => apiRequest<University[]>(`/universities${listQuery(params)}`),
    placeholderData: keepPreviousData,
  });

/**
 * One university. The contract has no GET /universities/{id}, so it is read
 * from the scope-limited list (including inactive records); `data` is null
 * when the record is absent or outside the user's scope.
 */
export const useUniversity = (id: number) =>
  useQuery({
    queryKey: catalogKeys.universityList({ include_inactive: true }),
    queryFn: () =>
      apiRequest<University[]>(`/universities${listQuery({ include_inactive: true })}`),
    select: (list) => list.find((u) => u.id === id) ?? null,
  });

export function useSaveUniversity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: UniversityInput }) =>
      id === undefined
        ? apiRequest<University>("/universities", "POST", data)
        : apiRequest<University>(`/universities/${id}`, "PATCH", data),
    onSuccess: (_data, { id }) => {
      invalidatePrefix(client, catalogKeys.universities);
      void client.invalidateQueries({ queryKey: queryKeys.dashboard, exact: true });
      // Contracts show the university name.
      if (id !== undefined) invalidatePrefix(client, catalogKeys.contracts);
      invalidateAudit(client);
    },
  });
}

export function useSetUniversityManagers() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, userIds }: { id: number; userIds: number[] }) =>
      apiRequest<University>(`/universities/${id}/managers`, "PUT", {
        user_ids: userIds,
      }),
    onSuccess: () => {
      invalidatePrefix(client, catalogKeys.universities);
      invalidateAudit(client);
    },
  });
}

/** CRM users with a role (supervisors and admins only). */
export const useCrmUsers = (role: string, enabled = true) =>
  useQuery({
    queryKey: catalogKeys.users(role),
    queryFn: () => apiRequest<CrmUser[]>(`/users${buildQuery({ role })}`),
    enabled,
  });

/* Ответственные от вуза */

export const useUniversityContacts = (
  universityId: number | undefined,
  params: ListParams = {},
) =>
  useQuery({
    queryKey: catalogKeys.contactList(universityId ?? 0, params),
    queryFn: () =>
      apiRequest<UniversityContact[]>(
        `/universities/${universityId}/contacts${buildQuery({
          include_inactive: params.include_inactive,
        })}`,
      ),
    enabled: universityId !== undefined,
  });

export function useSaveContact(universityId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: UniversityContactInput }) =>
      id === undefined
        ? apiRequest<UniversityContact>(
            `/universities/${universityId}/contacts`,
            "POST",
            data,
          )
        : apiRequest<UniversityContact>(`/university-contacts/${id}`, "PATCH", data),
    onSuccess: (_data, { id }) => {
      invalidatePrefix(client, catalogKeys.contacts(universityId));
      // Contracts list contact names.
      if (id !== undefined) invalidatePrefix(client, catalogKeys.contracts);
      invalidateAudit(client);
    },
  });
}

/* Договоры */

/** Request query of GET /contracts, in a stable parameter order. */
export const contractsQuery = (f: ContractFilters) =>
  buildQuery({
    q: f.q?.trim(),
    university_id: f.university_id,
    it_product_id: f.it_product_id,
    it_direction_id: f.it_direction_id,
    manager_user_id: f.manager_user_id,
    transfer_status: f.transfer_status,
    signed_from: f.signed_from,
    signed_to: f.signed_to,
    limit: f.limit ?? PAGE_SIZE,
    offset: f.offset ?? 0,
  });

export const useContracts = (filters: ContractFilters) =>
  useQuery({
    queryKey: catalogKeys.contractList(filters),
    queryFn: () => apiRequest<Page<Contract>>(`/contracts${contractsQuery(filters)}`),
    placeholderData: keepPreviousData,
  });

export const useTransferStatuses = () =>
  useQuery({
    queryKey: catalogKeys.transferStatuses,
    queryFn: () => apiRequest<TransferStatus[]>("/contracts/transfer-statuses"),
    staleTime: Infinity,
  });

export function useSaveContract() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: ContractInput }) =>
      id === undefined
        ? apiRequest<Contract>("/contracts", "POST", data)
        : apiRequest<Contract>(`/contracts/${id}`, "PATCH", data),
    onSuccess: () => {
      invalidatePrefix(client, catalogKeys.contracts);
      invalidateAudit(client);
    },
  });
}
