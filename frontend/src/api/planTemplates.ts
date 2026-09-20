import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { invalidateAudit } from "./queries";
import type { Task, TaskPriority } from "./tasks";
import type { PersonRef } from "./types";

/* Types of backend/app/plan_routes.py (docs/design/tasks.md) */

export type AssigneeRule = "specific_user" | "interaction_owner" | "university_manager" | "plan_creator" | "manual";
export type OffsetUnit = "calendar" | "business";

export const ASSIGNEE_RULE_LABELS: Record<AssigneeRule, string> = {
  specific_user: "Конкретный пользователь",
  interaction_owner: "Ответственный по взаимодействию",
  university_manager: "Менеджер вуза",
  plan_creator: "Автор плана",
  manual: "Назначается вручную",
};

export const OFFSET_UNIT_LABELS: Record<OffsetUnit, string> = {
  calendar: "календарных",
  business: "рабочих",
};

export interface TemplateStepChecklistItem {
  id: number;
  title: string;
  position: number;
}

export interface TemplateStep {
  id: number;
  position: number;
  title: string;
  description: string;
  assignee_rule: AssigneeRule;
  assignee_rule_user_id: number | null;
  start_offset_days: number;
  deadline_offset_days: number | null;
  offset_unit: OffsetUnit;
  priority: TaskPriority;
  approval_required: boolean;
  is_optional: boolean;
  depends_on_step_id: number | null;
  checklist_items: TemplateStepChecklistItem[];
}

export interface PlanTemplate {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  created_at: string;
  steps: TemplateStep[];
}

export interface TemplateStepInput {
  title: string;
  description?: string;
  assignee_rule: AssigneeRule;
  assignee_rule_user_id?: number | null;
  start_offset_days: number;
  deadline_offset_days?: number | null;
  offset_unit: OffsetUnit;
  priority?: TaskPriority;
  approval_required?: boolean;
  is_optional?: boolean;
  checklist_items?: string[];
}

export interface TemplateInput {
  name: string;
  description?: string;
  steps: (TemplateStepInput & { depends_on_position?: number | null })[];
}

const templateKeys = {
  all: ["plan-templates"] as const,
  list: (includeInactive: boolean) => ["plan-templates", "list", includeInactive] as const,
};

function afterTemplateChange(client: QueryClient) {
  void client.invalidateQueries({ queryKey: templateKeys.all });
  invalidateAudit(client);
}

export const usePlanTemplates = (includeInactive = false) =>
  useQuery({
    queryKey: templateKeys.list(includeInactive),
    queryFn: () => apiRequest<PlanTemplate[]>(`/task-plan-templates${includeInactive ? "?include_inactive=true" : ""}`),
  });

export function useCreateTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: TemplateInput) => apiRequest<PlanTemplate>("/task-plan-templates", "POST", data),
    onSuccess: () => afterTemplateChange(client),
  });
}

export function useUpdateTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: number; name?: string; description?: string; is_active?: boolean }) =>
      apiRequest<PlanTemplate>(`/task-plan-templates/${id}`, "PATCH", data),
    onSuccess: () => afterTemplateChange(client),
  });
}

export function useAddTemplateStep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, ...data }: { templateId: number } & TemplateStepInput & { depends_on_step_id?: number | null }) =>
      apiRequest<PlanTemplate>(`/task-plan-templates/${templateId}/steps`, "POST", data),
    onSuccess: () => afterTemplateChange(client),
  });
}

export function useUpdateTemplateStep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, ...data }: { stepId: number } & Partial<TemplateStepInput> & { depends_on_step_id?: number | null }) =>
      apiRequest<PlanTemplate>(`/task-plan-template-steps/${stepId}`, "PATCH", data),
    onSuccess: () => afterTemplateChange(client),
  });
}

export function useDeleteTemplateStep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (stepId: number) => apiRequest<PlanTemplate>(`/task-plan-template-steps/${stepId}`, "DELETE"),
    onSuccess: () => afterTemplateChange(client),
  });
}

export function useReorderTemplateSteps() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, stepIds }: { templateId: number; stepIds: number[] }) =>
      apiRequest<PlanTemplate>(`/task-plan-templates/${templateId}/steps-order`, "PUT", { step_ids: stepIds }),
    onSuccess: () => afterTemplateChange(client),
  });
}

/* Preview and generation */

export interface PlanRequest {
  university_id: number;
  launch_id?: number | null;
  start_date: string;
  assignee_overrides?: Record<string, number>;
}

export interface PreviewStep {
  step_id: number;
  title: string;
  description: string;
  assignee: PersonRef | null;
  assignee_issue: string | null;
  planned_start: string;
  deadline: string | null;
  priority: TaskPriority;
  approval_required: boolean;
  is_optional: boolean;
  depends_on_step_id: number | null;
  checklist_items: string[];
}

export interface PlanPreview {
  template_id: number;
  template_name: string;
  steps: PreviewStep[];
}

export function usePreviewPlan(templateId: number) {
  return useMutation({
    mutationFn: (data: PlanRequest) => apiRequest<PlanPreview>(`/task-plan-templates/${templateId}/preview`, "POST", data),
  });
}

export interface GenerateResult {
  run_id: number;
  tasks: Task[];
}

export function useGeneratePlan(templateId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: PlanRequest & { skip_step_ids?: number[] }) =>
      apiRequest<GenerateResult>(`/task-plan-templates/${templateId}/generate`, "POST", data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["tasks"] });
      void client.invalidateQueries({ queryKey: ["plan-runs"] });
      invalidateAudit(client);
    },
  });
}

/* Runs and progress */

export interface PlanProgress {
  total: number;
  completed: number;
  awaiting_review: number;
  overdue: number;
  blocked: number;
}

export interface PlanRun {
  id: number;
  template_id: number;
  template_name: string;
  university_id: number;
  launch_id: number | null;
  start_date: string;
  started_by: PersonRef | null;
  created_at: string;
  progress: PlanProgress;
}

export const useUniversityPlanRuns = (universityId: number) =>
  useQuery({
    queryKey: ["plan-runs", universityId] as const,
    queryFn: () => apiRequest<PlanRun[]>(`/task-plan-runs?university_id=${universityId}`),
    enabled: Number.isInteger(universityId) && universityId > 0,
  });
