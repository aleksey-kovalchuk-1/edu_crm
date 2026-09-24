/** Short reference to a related record ({id, name} or {id, full_name}). */
export interface NamedRef {
  id: number;
  name: string;
}
export interface PersonRef {
  id: number;
  full_name: string;
}
/** Paginated list response: {items, total, limit, offset}. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface University {
  id: number;
  name: string;
  short_name: string;
  city: string;
  region: string;
  website: string;
  /** Legacy free-text contact field. */
  contact: string;
  is_active: boolean;
  /** Responsible CRM users (ответственные от ИТ-школы). */
  managers: PersonRef[];
}
export interface UniversityInput {
  name?: string;
  city?: string;
  short_name?: string;
  region?: string;
  website?: string;
  contact?: string;
  is_active?: boolean;
}

export interface ITDirection {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
}
export interface ITDirectionInput {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export interface ITProduct {
  id: number;
  vendor: string;
  name: string;
  description: string;
  is_active: boolean;
  directions: NamedRef[];
}
export interface ITProductInput {
  vendor?: string;
  name?: string;
  description?: string;
  direction_ids?: number[];
  is_active?: boolean;
}

/** Entry of GET /users. */
export interface CrmUser {
  id: number;
  full_name: string;
  email: string;
  roles: string[];
  is_active: boolean;
}

/** Ответственный от вуза. */
export interface UniversityContact {
  id: number;
  university_id: number;
  full_name: string;
  position: string;
  email: string;
  phone: string;
  comment: string;
  is_active: boolean;
}
export interface UniversityContactInput {
  full_name?: string;
  position?: string;
  email?: string;
  phone?: string;
  comment?: string;
  is_active?: boolean;
}

export interface TransferStatus {
  value: string;
  label: string;
}

export interface Contract {
  id: number;
  contract_number: string;
  university: NamedRef;
  it_product: { id: number; vendor: string; name: string };
  signed_at: string;
  valid_until: string;
  transfer_status: string;
  transfer_status_label: string;
  manager: PersonRef | null;
  /** Imported manager name that did not match a CRM user. */
  manager_name: string;
  contacts: PersonRef[];
  comment: string;
  is_expired: boolean;
  expires_soon: boolean;
  updated_at: string;
}
export interface ContractInput {
  contract_number?: string;
  university_id?: number;
  it_product_id?: number;
  signed_at?: string;
  valid_until?: string;
  transfer_status?: string;
  manager_user_id?: number | null;
  contact_ids?: number[];
  comment?: string;
}
/** Filters of GET /contracts (all optional). */
export interface ContractFilters {
  q?: string;
  university_id?: number;
  it_product_id?: number;
  it_direction_id?: number;
  manager_user_id?: number;
  transfer_status?: string;
  signed_from?: string;
  signed_to?: string;
  limit?: number;
  offset?: number;
}
export interface Launch {
  id: number;
  university_id: number;
  university: string;
  city: string;
  program: string;
  product: string;
  owner: string;
  students: number;
  stage: number;
  deadline: string;
  overdue: boolean;
  /** Workflow template and current status (T-040); may be absent in older responses. */
  workflow_template_id?: number | null;
  status_id?: number | null;
  /** Catalog IT product used by reports (D-221); `product` stays the free-text description. */
  it_product_id?: number | null;
}
export interface StageEvent {
  id: number;
  stage: number;
  created_at: string;
}
export interface AnnualMetric {
  year: number;
  applications: number;
  students: number;
  streams: number;
}
export interface Dashboard {
  universities: number;
  launches: number;
  students: number;
  overdue: number;
  annual: AnnualMetric[];
}
/** One entry of GET /audit/recent (newest first). */
export interface AuditEvent {
  id: number;
  occurred_at: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  summary: string;
  user: { id: number; full_name: string } | null;
}
export interface LaunchInput {
  university_id: number;
  program: string;
  product: string;
  owner: string;
  students: number;
  deadline: string;
  it_product_id?: number;
}
