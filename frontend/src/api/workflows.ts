import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { formatFileSize } from "./imports";
import { invalidate, invalidateAudit, queryKeys } from "./queries";
import type { Launch, NamedRef, PersonRef } from "./types";

/* Types of backend/app/workflow_routes.py (docs/design/workflows.md) */

export interface WorkflowStatus {
  id: number;
  name: string;
  position: number;
  is_final: boolean;
  is_active: boolean;
}

export interface Workflow {
  id: number;
  name: string;
  description: string;
  is_default: boolean;
  is_active: boolean;
  statuses: WorkflowStatus[];
}

export interface Attachment {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface StatusChange {
  id: number;
  launch_id: number;
  from_status: NamedRef | null;
  to_status: NamedRef;
  comment: string;
  author: PersonRef | null;
  created_at: string;
  attachments: Attachment[];
}

export interface StatusChangeInput {
  status_id: number;
  comment: string;
  files: File[];
}

/* Limits mirrored from the server (it checks again, including file content) */

export const MAX_COMMENT_LENGTH = 2000;
export const MAX_ATTACHMENTS = 5;
export const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
export const ATTACHMENT_EXTENSIONS = [
  "png", "jpg", "jpeg", "pdf", "zip", "gz", "gzip", "rar", "doc", "docx", "xls", "xlsx",
];
export const ATTACHMENT_ACCEPT = ATTACHMENT_EXTENSIONS.map((e) => `.${e}`).join(",");
export const ATTACHMENT_FORMATS_TEXT = "png, jpg, pdf, zip, gz, rar, doc, docx, xls, xlsx";

export const attachmentUrl = (id: number) => `/api/v1/attachments/${id}`;

/** Russian message when a file cannot be attached, otherwise null. */
export function attachmentProblem(file: File): string | null {
  const extension = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!ATTACHMENT_EXTENSIONS.includes(extension)) {
    return `Файл «${file.name}» не подходит: допустимые форматы — ${ATTACHMENT_FORMATS_TEXT}.`;
  }
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return `Файл «${file.name}» весит ${formatFileSize(file.size)} — это больше допустимых 20 МБ.`;
  }
  if (file.size === 0) return `Файл «${file.name}» пустой.`;
  return null;
}

/** Adds chosen files to the selection; rejected ones come back with messages. */
export function addAttachments(current: File[], chosen: File[]) {
  const files = [...current];
  const errors: string[] = [];
  for (const file of chosen) {
    const problem = attachmentProblem(file);
    if (problem) errors.push(problem);
    else if (files.length >= MAX_ATTACHMENTS)
      errors.push(`Файл «${file.name}» не добавлен: не больше ${MAX_ATTACHMENTS} файлов за одну смену статуса.`);
    else files.push(file);
  }
  return { files, errors };
}

/* Workflow helpers */

export const defaultWorkflow = (workflows: Workflow[]) =>
  workflows.find((w) => w.is_default) ?? workflows[0];

export const sortedStatuses = (workflow: Workflow) =>
  [...workflow.statuses].sort((a, b) => a.position - b.position);

/** The launch's workflow; launches without one fall back to the default workflow. */
export const launchWorkflow = (workflows: Workflow[], launch: Launch) =>
  workflows.find((w) => w.id === launch.workflow_template_id) ?? defaultWorkflow(workflows);

/** Current status by status_id; older data without it — by the stage position. */
export function currentStatus(workflow: Workflow | undefined, launch: Launch) {
  if (!workflow) return undefined;
  if (launch.status_id != null) return workflow.statuses.find((s) => s.id === launch.status_id);
  return workflow.statuses.find((s) => s.position === launch.stage);
}

export interface BoardColumn {
  key: string;
  title: string;
  status: WorkflowStatus | null;
  launches: Launch[];
}

/**
 * Board columns of a workflow in position order. Inactive statuses are shown
 * only while they hold launches; launches of other workflows go to a last column.
 */
export function groupByStatus(workflow: Workflow, launches: Launch[]): BoardColumn[] {
  const columns: BoardColumn[] = [];
  const placed = new Set<number>();
  for (const status of sortedStatuses(workflow)) {
    const items = launches.filter(
      (l) => (l.workflow_template_id ?? workflow.id) === workflow.id && currentStatus(workflow, l)?.id === status.id,
    );
    items.forEach((l) => placed.add(l.id));
    if (status.is_active || items.length)
      columns.push({ key: `status-${status.id}`, title: status.name, status, launches: items });
  }
  const others = launches.filter((l) => !placed.has(l.id));
  if (others.length) columns.push({ key: "other", title: "Другие процессы", status: null, launches: others });
  return columns;
}

/* Queries */

export const workflowKeys = {
  all: ["workflows"] as const,
  statusChanges: (launchId: number) => ["status-changes", launchId] as const,
};

export const useWorkflows = () =>
  useQuery({
    queryKey: workflowKeys.all,
    queryFn: () => apiRequest<Workflow[]>("/workflows"),
  });

export const useStatusChanges = (launchId: number) =>
  useQuery({
    queryKey: workflowKeys.statusChanges(launchId),
    queryFn: () => apiRequest<StatusChange[]>(`/launches/${launchId}/status-changes`),
    enabled: Number.isInteger(launchId) && launchId > 0,
  });

export function useChangeStatus(launchId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ status_id, comment, files }: StatusChangeInput) => {
      const form = new FormData();
      form.append("status_id", String(status_id));
      form.append("comment", comment);
      for (const file of files) form.append("files", file, file.name);
      return apiRequest<StatusChange>(`/launches/${launchId}/status-changes`, "POST", form);
    },
    onSuccess: () => {
      invalidate(
        client,
        queryKeys.launches,
        workflowKeys.statusChanges(launchId),
        queryKeys.dashboard,
      );
      invalidateAudit(client);
    },
  });
}

/** Workflow edits rename or move statuses that launches and older stage screens show. */
function afterWorkflowEdit(client: QueryClient) {
  invalidate(client, workflowKeys.all, queryKeys.stages, queryKeys.launches);
  invalidateAudit(client);
}

export interface WorkflowInput {
  name: string;
  description: string;
  statuses: string[];
}

export function useCreateWorkflow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: WorkflowInput) => apiRequest<Workflow>("/workflows", "POST", data),
    onSettled: () => afterWorkflowEdit(client),
  });
}

export function useUpdateWorkflow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: number; name?: string; description?: string; is_active?: boolean }) =>
      apiRequest<Workflow>(`/workflows/${id}`, "PATCH", data),
    onSettled: () => afterWorkflowEdit(client),
  });
}

export function useAddStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ workflowId, ...data }: { workflowId: number; name: string; is_final: boolean }) =>
      apiRequest<WorkflowStatus>(`/workflows/${workflowId}/statuses`, "POST", data),
    onSettled: () => afterWorkflowEdit(client),
  });
}

export function useUpdateStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: number; name?: string; is_final?: boolean; is_active?: boolean }) =>
      apiRequest<WorkflowStatus>(`/workflow-statuses/${id}`, "PATCH", data),
    onSettled: () => afterWorkflowEdit(client),
  });
}

export function useReorderStatuses() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ workflowId, status_ids }: { workflowId: number; status_ids: number[] }) =>
      apiRequest<Workflow>(`/workflows/${workflowId}/status-order`, "PUT", { status_ids }),
    onSettled: () => afterWorkflowEdit(client),
  });
}
