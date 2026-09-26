import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { catalogKeys } from "./catalogs";
import { invalidateAudit } from "./queries";

export interface VendorCompany { id: number; name: string; is_active: boolean }
export interface VendorContact {
  id: number; company_id: number; full_name: string; phone: string; email: string;
  preferred_channels: string[]; product_ids: number[]; is_active: boolean;
}
export interface LearnerSummary {
  id: number; last_name: string; first_name: string; middle_name: string; phone: string; email: string;
}
export interface LearnerFull extends LearnerSummary {
  snils: string | null; passport_series: string | null; passport_number: string | null;
  passport_issued_by: string | null; passport_issued_at: string | null;
  passport_department_code: string | null; gender: string | null; birth_date: string | null;
  registration_region: string | null; registration_locality: string | null;
  registration_street: string | null; registration_house: string | null;
  registration_apartment: string | null; postal_code: string | null;
  dative_first_name: string | null; dative_last_name: string | null;
  dative_middle_name: string | null; education: string | null;
  diploma_profession: string | null; diploma_institution: string | null;
  diploma_last_name: string | null; diploma_number: string | null;
  diploma_series: string | null; diploma_registration_number: string | null;
  diploma_issued_at: string | null;
}
export interface CourseApplication {
  id: number; external_number: string; course: string; stream_number: string;
  learner_id: number; learner_name: string; payment_status: string; payment_status_label: string;
}
export type ImportKind = "vendors" | "learners" | "applications";
export interface ImportRow {
  row_number: number; status: "ok" | "error" | "skipped";
  action: "created" | "updated" | null; errors: string[]; warnings: string[]; candidate_ids: number[];
  signals?: { rule_code: string; priority: "low" | "medium" | "high"; evidence_kind?: string | null }[];
}
export interface ImportReport {
  summary: { rows: number; valid: number; invalid: number; skipped: number; created: number; updated: number };
  rows: ImportRow[];
  template_version?: string;
  mapping?: Record<string, string>;
  unmapped_headers?: string[];
  mapping_conflicts?: Record<string, string[]>;
  batch_signals?: ImportRow["signals"];
  batch_id?: number;
  record_links?: { row_number: number; entity_type: "vendor_contact" | "learner" | "course_application"; entity_id: number; action: "created" | "updated" }[];
}
export interface ImportBatch { id: number; kind: ImportKind; template_version: string; created_at: string; summary: ImportReport["summary"] }

const query = (params: Record<string, string | number | boolean | undefined>) => {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== "");
  const text = new URLSearchParams(entries.map(([name, value]) => [name, String(value)])).toString();
  return text ? `?${text}` : "";
};

const keys = {
  companies: ["customer", "companies"] as const,
  contacts: ["customer", "contacts"] as const,
  learners: ["customer", "learners"] as const,
  applications: ["customer", "applications"] as const,
  importHistory: ["customer", "importHistory"] as const,
};

export const useVendorCompanies = (q = "", includeInactive = false) => useQuery({
  queryKey: [...keys.companies, q, includeInactive],
  queryFn: () => apiRequest<VendorCompany[]>(`/vendor-companies${query({ q, include_inactive: includeInactive || undefined })}`),
});
export const useVendorContacts = (companyId?: number, productId?: number, q = "", includeInactive = false) => useQuery({
  queryKey: [...keys.contacts, companyId, productId, q, includeInactive],
  queryFn: () => apiRequest<VendorContact[]>(`/vendor-contacts${query({ company_id: companyId, product_id: productId, q, include_inactive: includeInactive || undefined })}`),
});
export function useSaveVendorCompany() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: Partial<VendorCompany> }) => id
      ? apiRequest<VendorCompany>(`/vendor-companies/${id}`, "PATCH", data)
      : apiRequest<VendorCompany>("/vendor-companies", "POST", data),
    onSuccess: () => { void client.invalidateQueries({ queryKey: keys.companies }); invalidateAudit(client); },
  });
}
export function useSaveVendorContact() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: Partial<VendorContact> }) => id
      ? apiRequest<VendorContact>(`/vendor-contacts/${id}`, "PATCH", data)
      : apiRequest<VendorContact>("/vendor-contacts", "POST", data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.contacts });
      void client.invalidateQueries({ queryKey: catalogKeys.products });
      invalidateAudit(client);
    },
  });
}

export const useLearners = (q = "") => useQuery({
  queryKey: [...keys.learners, q],
  queryFn: () => apiRequest<LearnerSummary[]>(`/learners${query({ q })}`),
});
export const useLearner = (id?: number) => useQuery({
  queryKey: [...keys.learners, "detail", id],
  queryFn: () => apiRequest<LearnerFull>(`/learners/${id}`),
  enabled: id !== undefined,
});
export function useSaveLearner() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: Partial<LearnerFull> }) => id
      ? apiRequest<LearnerFull>(`/learners/${id}`, "PATCH", data)
      : apiRequest<LearnerFull>("/learners", "POST", data),
    onSuccess: () => { void client.invalidateQueries({ queryKey: keys.learners }); invalidateAudit(client); },
  });
}

export const useCourseApplications = (course = "", streamNumber = "") => useQuery({
  queryKey: [...keys.applications, course, streamNumber],
  queryFn: () => apiRequest<CourseApplication[]>(`/course-applications${query({ course, stream_number: streamNumber })}`),
});

function upload(kind: ImportKind, phase: "preview" | "apply", file: File, resolved?: Record<string, number>, mapping?: Record<string, string>) {
  const data = new FormData();
  data.append("file", file);
  if (resolved) data.append("resolved_learner_ids", JSON.stringify(resolved));
  if (mapping) data.append("mapping", JSON.stringify(mapping));
  return apiRequest<ImportReport>(`/customer-imports/${kind}/${phase}`, "POST", data);
}
export function usePreviewCustomerImport() {
  return useMutation({ mutationFn: ({ kind, file, mapping }: { kind: ImportKind; file: File; mapping?: Record<string, string> }) => upload(kind, "preview", file, undefined, mapping) });
}
export function useApplyCustomerImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, file, resolved, mapping }: { kind: ImportKind; file: File; resolved?: Record<string, number>; mapping?: Record<string, string> }) =>
      upload(kind, "apply", file, resolved, mapping),
    onSuccess: () => {
      for (const key of Object.values(keys)) void client.invalidateQueries({ queryKey: key });
      invalidateAudit(client);
    },
  });
}
export const useCustomerImportHistory = () => useQuery({
  queryKey: keys.importHistory,
  queryFn: () => apiRequest<ImportBatch[]>("/customer-imports/history"),
});
