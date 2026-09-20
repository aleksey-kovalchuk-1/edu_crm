import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ListTree, Play } from "lucide-react";
import {
  usePlanTemplates,
  usePreviewPlan,
  useGeneratePlan,
  useUniversityPlanRuns,
  type PlanPreview,
  type PlanRequest,
  type PlanRun,
} from "../../api/planTemplates";
import { errorText } from "../../api/client";
import { useAssignableUsers } from "../../api/tasks";
import { useLaunches } from "../../api/queries";
import { paths } from "../../app/navigation";
import { Modal } from "../Modal";
import { RefreshError, queryFallback } from "../QueryState";
import { FormFooter, formText } from "../forms/FormParts";

const dateLabel = (iso: string) => new Date(iso).toLocaleDateString("ru-RU");

function ProgressBar({ progress }: { progress: PlanRun["progress"] }) {
  const pct = progress.total ? Math.round((progress.completed / progress.total) * 100) : 0;
  return (
    <div className="plan-progress" aria-label={`Готово ${pct}%`}>
      <div className="plan-progress-bar">
        <div className="plan-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <small className="muted">
        {progress.completed}/{progress.total} задач
        {progress.awaiting_review ? ` · на согласовании: ${progress.awaiting_review}` : ""}
        {progress.overdue ? ` · просрочено: ${progress.overdue}` : ""}
        {progress.blocked ? ` · заблокировано: ${progress.blocked}` : ""}
      </small>
    </div>
  );
}

function PlanRunCard({ run }: { run: PlanRun }) {
  return (
    <li className="plan-run">
      <div>
        <strong>{run.template_name}</strong>
        <small className="muted">
          Старт {dateLabel(run.start_date)}
          {run.started_by && ` · запустил ${run.started_by.full_name}`}
        </small>
      </div>
      <ProgressBar progress={run.progress} />
      <Link className="text-button" to={`${paths.tasks}?university_id=${run.university_id}`}>
        Задачи плана
      </Link>
    </li>
  );
}

function StepAssigneeOverride({
  step,
  value,
  onChange,
}: {
  step: PlanPreview["steps"][number];
  value: number | undefined;
  onChange: (userId: number) => void;
}) {
  const users = useAssignableUsers();
  return (
    <label className="plan-step-override">
      {step.assignee_issue || "Назначить исполнителя"}
      <select value={value ?? ""} onChange={(e) => e.target.value && onChange(Number(e.target.value))} required>
        <option value="" disabled>
          Выберите
        </option>
        {users.data?.map((u) => (
          <option value={u.id} key={u.id}>
            {u.full_name}
          </option>
        ))}
      </select>
    </label>
  );
}

interface StartRequest {
  templateId: number;
  templateName: string;
  body: PlanRequest;
}

function SelectTemplateStep({ universityId, close, onReady }: { universityId: number; close: () => void; onReady: (req: StartRequest) => void }) {
  const templates = usePlanTemplates();
  const launches = useLaunches();
  const universityLaunches = (launches.data ?? []).filter((l) => l.university_id === universityId);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <Modal title="Запустить план задач" close={close}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const templateId = Number(formText(f, "template_id"));
          const template = templates.data?.find((t) => t.id === templateId);
          if (!template) return;
          const launchId = formText(f, "launch_id");
          onReady({
            templateId,
            templateName: template.name,
            body: {
              university_id: universityId,
              launch_id: launchId ? Number(launchId) : null,
              start_date: formText(f, "start_date"),
            },
          });
        }}
      >
        <label>
          Шаблон плана
          <select name="template_id" required disabled={templates.isLoading} defaultValue="">
            <option value="" disabled>
              Выберите шаблон
            </option>
            {templates.data
              ?.filter((t) => t.is_active)
              .map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          Дата старта
          <input type="date" name="start_date" defaultValue={today} required />
        </label>
        <label>
          Связанное взаимодействие (необязательно)
          <select name="launch_id" defaultValue="">
            <option value="">Не привязывать</option>
            {universityLaunches.map((l) => (
              <option value={l.id} key={l.id}>
                {l.program} · {l.product}
              </option>
            ))}
          </select>
        </label>
        <FormFooter error={undefined} pending={false} onCancel={close} submitLabel="Предпросмотр" />
      </form>
    </Modal>
  );
}

function PreviewAndGenerateStep({ request, close, onBack }: { request: StartRequest; close: () => void; onBack: () => void }) {
  const previewMutation = usePreviewPlan(request.templateId);
  const generate = useGeneratePlan(request.templateId);
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [overrides, setOverrides] = useState<Record<number, number>>({});
  const [skipped, setSkipped] = useState<Set<number>>(new Set());

  useEffect(() => {
    previewMutation.mutate(request.body, { onSuccess: setPreview });
    // Fetch the preview once, right when this step mounts with a fixed request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!preview) {
    return (
      <Modal title={`План «${request.templateName}»`} close={close}>
        {previewMutation.error ? (
          <p className="danger" role="alert">
            {errorText(previewMutation.error)}
          </p>
        ) : (
          <p className="empty">Строим предпросмотр…</p>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onBack}>
            Назад
          </button>
        </div>
      </Modal>
    );
  }

  const requiredMissing = preview.steps.some((s) => !skipped.has(s.step_id) && !s.assignee && !overrides[s.step_id]);

  return (
    <Modal title={`План «${preview.template_name}»`} close={close} wide>
      {generate.error ? (
        <p className="danger" role="alert">
          {errorText(generate.error)}
        </p>
      ) : null}
      <ul className="plan-preview-steps">
        {preview.steps.map((s) => (
          <li key={s.step_id} className="plan-preview-step">
            <div className="template-step-head">
              <strong>{s.title}</strong>
              <span className="muted">
                {dateLabel(s.planned_start)}
                {s.deadline && ` — срок ${dateLabel(s.deadline)}`}
              </span>
              <span className="muted">
                {s.assignee ? s.assignee.full_name : "Исполнитель не определён"}
                {s.is_optional && " · необязательный"}
              </span>
            </div>
            {s.is_optional && (
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={skipped.has(s.step_id)}
                  onChange={(e) =>
                    setSkipped((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(s.step_id);
                      else next.delete(s.step_id);
                      return next;
                    })
                  }
                />
                Пропустить этот шаг
              </label>
            )}
            {!s.assignee && !skipped.has(s.step_id) && (
              <StepAssigneeOverride
                step={s}
                value={overrides[s.step_id]}
                onChange={(userId) => setOverrides((prev) => ({ ...prev, [s.step_id]: userId }))}
              />
            )}
          </li>
        ))}
      </ul>
      <div className="modal-actions">
        <button type="button" className="secondary" onClick={onBack}>
          Назад
        </button>
        <button
          type="button"
          className="primary"
          disabled={requiredMissing || generate.isPending}
          onClick={() =>
            generate.mutate(
              {
                ...request.body,
                assignee_overrides: Object.fromEntries(Object.entries(overrides).map(([k, v]) => [k, v])),
                skip_step_ids: [...skipped],
              },
              { onSuccess: close },
            )
          }
        >
          {generate.isPending ? "Создаём…" : "Создать задачи"}
        </button>
      </div>
    </Modal>
  );
}

function StartPlanWizard({ universityId, close }: { universityId: number; close: () => void }) {
  const [request, setRequest] = useState<StartRequest | null>(null);
  if (!request) return <SelectTemplateStep universityId={universityId} close={close} onReady={setRequest} />;
  return <PreviewAndGenerateStep request={request} close={close} onBack={() => setRequest(null)} />;
}

export function TaskPlanSection({ universityId }: { universityId: number }) {
  const runs = useUniversityPlanRuns(universityId);
  const [wizardOpen, setWizardOpen] = useState(false);
  const fallback = queryFallback([runs]);

  return (
    <section className="panel" aria-labelledby="task-plans-title">
      <div className="section-head">
        <div>
          <h2 id="task-plans-title">Планы задач</h2>
          <p>Запуск типовых последовательностей задач и их прогресс</p>
        </div>
        <div className="head-actions">
          <Link className="text-button" to={paths.taskTemplates}>
            <ListTree size={15} /> Шаблоны
          </Link>
          <button type="button" className="secondary" onClick={() => setWizardOpen(true)}>
            <Play size={15} /> Запустить план
          </button>
        </div>
      </div>
      <RefreshError queries={[runs]} />
      {fallback ?? (
        <ul className="plan-runs">
          {runs.data?.map((r) => (
            <PlanRunCard run={r} key={r.id} />
          ))}
          {runs.data && !runs.data.length && <p className="empty">Планы ещё не запускались.</p>}
        </ul>
      )}
      {wizardOpen && <StartPlanWizard universityId={universityId} close={() => setWizardOpen(false)} />}
    </section>
  );
}
