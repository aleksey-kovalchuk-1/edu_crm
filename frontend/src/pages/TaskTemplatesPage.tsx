import { useState } from "react";
import { Link } from "react-router";
import { ArrowDown, ArrowLeft, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import {
  ASSIGNEE_RULE_LABELS,
  OFFSET_UNIT_LABELS,
  useAddTemplateStep,
  useCreateTemplate,
  useDeleteTemplateStep,
  usePlanTemplates,
  useReorderTemplateSteps,
  useUpdateTemplate,
  useUpdateTemplateStep,
  type PlanTemplate,
  type TemplateStep,
} from "../api/planTemplates";
import { TASK_PRIORITY_LABELS } from "../api/tasks";
import { useSession } from "../app/AuthGate";
import { paths } from "../app/navigation";
import { Modal } from "../components/Modal";
import { FormFooter, formText } from "../components/forms/FormParts";
import { RefreshError, queryFallback } from "../components/QueryState";
import { TemplateStepForm } from "../components/tasks/TemplateStepForm";
import { canEditWorkflows } from "../lib/user";
import { FORBIDDEN_TITLE } from "./ImportsPage";

function CreateTemplateForm({ onDone }: { onDone: (id: number) => void }) {
  const create = useCreateTemplate();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        create.mutate(
          { name: formText(f, "name"), description: formText(f, "description"), steps: [] },
          { onSuccess: (t) => onDone(t.id) },
        );
      }}
    >
      <label>
        Название шаблона
        <input name="name" required maxLength={200} autoFocus />
      </label>
      <label>
        Описание
        <textarea name="description" rows={2} maxLength={2000} />
      </label>
      <p className="form-note">Шаги добавляются после создания шаблона.</p>
      <FormFooter error={create.error} pending={create.isPending} onCancel={() => onDone(-1)} submitLabel="Создать" />
    </form>
  );
}

function TemplateStepsList({ template }: { template: PlanTemplate }) {
  const reorder = useReorderTemplateSteps();
  const steps = [...template.steps].sort((a, b) => a.position - b.position);

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= steps.length) return;
    const ids = steps.map((s) => s.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate({ templateId: template.id, stepIds: ids });
  }

  return (
    <ul className="template-steps">
      {steps.map((step, index) => (
        <li key={step.id} className={step.is_optional ? "template-step optional" : "template-step"}>
          <div className="template-step-head">
            <strong>{step.title}</strong>
            <span className="muted">
              {ASSIGNEE_RULE_LABELS[step.assignee_rule]} · {TASK_PRIORITY_LABELS[step.priority]}
              {step.approval_required && " · с согласованием"}
              {step.is_optional && " · необязательный"}
            </span>
            <span className="muted">
              Начало +{step.start_offset_days} {OFFSET_UNIT_LABELS[step.offset_unit]}
              {step.deadline_offset_days != null && `, срок +${step.deadline_offset_days}`}
            </span>
          </div>
          <div className="template-step-actions">
            <button type="button" className="icon-button" aria-label={`Переместить «${step.title}» выше`} disabled={index === 0 || reorder.isPending} onClick={() => move(index, -1)}>
              <ArrowUp size={14} />
            </button>
            <button type="button" className="icon-button" aria-label={`Переместить «${step.title}» ниже`} disabled={index === steps.length - 1 || reorder.isPending} onClick={() => move(index, 1)}>
              <ArrowDown size={14} />
            </button>
            <StepEditButton step={step} />
          </div>
        </li>
      ))}
      {!steps.length && <p className="empty">Шагов пока нет.</p>}
    </ul>
  );
}

function StepEditButton({ step }: { step: TemplateStep }) {
  const [editing, setEditing] = useState(false);
  const update = useUpdateTemplateStep();
  const remove = useDeleteTemplateStep();
  return (
    <>
      <button type="button" className="icon-button" aria-label={`Изменить «${step.title}»`} onClick={() => setEditing(true)}>
        <Pencil size={14} />
      </button>
      <button type="button" className="icon-button" aria-label={`Удалить «${step.title}»`} disabled={remove.isPending} onClick={() => remove.mutate(step.id)}>
        <Trash2 size={14} />
      </button>
      {editing && (
        <Modal title={`Шаг «${step.title}»`} close={() => setEditing(false)}>
          <TemplateStepForm
            initial={step}
            pending={update.isPending}
            error={update.error}
            onCancel={() => setEditing(false)}
            onSubmit={(data) => update.mutate({ stepId: step.id, ...data }, { onSuccess: () => setEditing(false) })}
          />
        </Modal>
      )}
    </>
  );
}

function TemplateCard({ template }: { template: PlanTemplate }) {
  const [expanded, setExpanded] = useState(false);
  const [addingStep, setAddingStep] = useState(false);
  const toggleActive = useUpdateTemplate();
  const addStep = useAddTemplateStep();

  return (
    <section className="panel template-card">
      <div className="section-head">
        <div>
          <h2>
            {template.name}
            {!template.is_active && <span className="badge badge-4 inline-badge">Неактивен</span>}
          </h2>
          {template.description && <p>{template.description}</p>}
          <small className="muted">{template.steps.length} шагов</small>
        </div>
        <div className="head-actions">
          <button
            type="button"
            className="secondary"
            disabled={toggleActive.isPending}
            onClick={() => toggleActive.mutate({ id: template.id, is_active: !template.is_active })}
          >
            {template.is_active ? "Деактивировать" : "Активировать"}
          </button>
          <button type="button" className="secondary" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Свернуть" : "Шаги"}
          </button>
        </div>
      </div>
      {expanded && (
        <>
          <TemplateStepsList template={template} />
          {addingStep ? (
            <TemplateStepForm
              pending={addStep.isPending}
              error={addStep.error}
              onCancel={() => setAddingStep(false)}
              onSubmit={(data) =>
                addStep.mutate(
                  { templateId: template.id, ...data, depends_on_step_id: template.steps.at(-1)?.id ?? null },
                  { onSuccess: () => setAddingStep(false) },
                )
              }
            />
          ) : (
            <button type="button" className="secondary" onClick={() => setAddingStep(true)}>
              <Plus size={15} /> Добавить шаг
            </button>
          )}
        </>
      )}
    </section>
  );
}

export function TaskTemplatesPage() {
  const { user } = useSession();
  if (!canEditWorkflows(user.roles)) {
    return (
      <section className="panel">
        <div className="empty forbidden">
          <h2>{FORBIDDEN_TITLE}</h2>
          <p>
            Редактирование шаблонов планов доступно руководителю и администратору. Если вам нужен
            доступ, обратитесь к администратору CRM.
          </p>
        </div>
      </section>
    );
  }
  return <TaskTemplatesEditor />;
}

function TaskTemplatesEditor() {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [creating, setCreating] = useState(false);
  const templates = usePlanTemplates(includeInactive);
  const fallback = queryFallback([templates]);

  return (
    <>
      <div className="detail-links">
        <Link className="back-link text-button" to={paths.tasks}>
          <ArrowLeft size={16} />К задачам
        </Link>
      </div>
      <RefreshError queries={[templates]} />
      <div className="toolbar">
        <label className="toggle">
          <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
          Показать неактивные
        </label>
        <button type="button" className="primary" onClick={() => setCreating(true)}>
          <Plus size={18} />
          Создать шаблон
        </button>
      </div>
      {fallback ?? (
        <>
          {templates.data?.map((t) => (
            <TemplateCard template={t} key={t.id} />
          ))}
          {templates.data && !templates.data.length && <p className="empty">Шаблонов пока нет.</p>}
        </>
      )}
      {creating && (
        <Modal title="Новый шаблон плана" close={() => setCreating(false)}>
          <CreateTemplateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
    </>
  );
}
