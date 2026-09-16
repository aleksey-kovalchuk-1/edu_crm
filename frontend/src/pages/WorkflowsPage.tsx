import { useState, type FormEvent } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import {
  sortedStatuses,
  useAddStatus,
  useCreateWorkflow,
  useReorderStatuses,
  useUpdateStatus,
  useUpdateWorkflow,
  useWorkflows,
  type Workflow,
} from "../api/workflows";
import { useSession } from "../app/AuthGate";
import { ErrorAlert, RefreshError, queryFallback } from "../components/QueryState";
import { fieldErrorMessage } from "../components/forms/FormParts";
import { canEditWorkflows } from "../lib/user";
import { FORBIDDEN_TITLE } from "./ImportsPage";

export function WorkflowsPage() {
  const { user } = useSession();
  if (!canEditWorkflows(user.roles)) {
    return (
      <section className="panel">
        <div className="empty forbidden">
          <h2>{FORBIDDEN_TITLE}</h2>
          <p>
            Настройка процессов доступна руководителю и администратору. Если вам нужен доступ,
            обратитесь к администратору CRM.
          </p>
        </div>
      </section>
    );
  }
  return <WorkflowEditor />;
}

function WorkflowEditor() {
  const workflows = useWorkflows();
  const fallback = queryFallback([workflows]);
  if (fallback || !workflows.data) return fallback;
  return (
    <>
      <RefreshError queries={[workflows]} />
      <div className="workflows-layout">
        <div className="workflow-list">
          {workflows.data.map((w) => (
            <WorkflowCard key={w.id} workflow={w} />
          ))}
          {!workflows.data.length && <div className="empty">Процессов пока нет.</div>}
        </div>
        <CreateWorkflowForm />
      </div>
    </>
  );
}

const statusLines = (text: string) =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

function CreateWorkflowForm() {
  const create = useCreateWorkflow();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [statuses, setStatuses] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const list = statusLines(statuses);
    if (!name.trim()) return setClientError("Укажите название процесса");
    if (!list.length) return setClientError("Добавьте хотя бы один статус");
    if (new Set(list).size !== list.length) return setClientError("Названия статусов не должны повторяться");
    setClientError(null);
    create.mutate(
      { name: name.trim(), description: description.trim(), statuses: list },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          setStatuses("");
        },
      },
    );
  };

  return (
    <section className="panel">
      <div className="section-head">
        <h2>Новый процесс</h2>
      </div>
      <form className="editor-form" onSubmit={submit} noValidate>
        <label>
          Название процесса
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          {fieldErrorMessage(create.error, "name") && (
            <small className="field-error danger">{fieldErrorMessage(create.error, "name")}</small>
          )}
        </label>
        <label>
          Описание
          <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
        </label>
        <label>
          Статусы — по одному на строке
          <textarea rows={6} value={statuses} onChange={(e) => setStatuses(e.target.value)} />
          <small className="field-hint">Последний статус станет финальным.</small>
          {fieldErrorMessage(create.error, "statuses") && (
            <small className="field-error danger">{fieldErrorMessage(create.error, "statuses")}</small>
          )}
        </label>
        {clientError && (
          <p className="danger" role="alert">
            {clientError}
          </p>
        )}
        {create.error && <ErrorAlert error={create.error} />}
        <div className="modal-actions">
          <button className="primary" disabled={create.isPending}>
            {create.isPending ? "Создаём…" : "Создать процесс"}
          </button>
        </div>
      </form>
    </section>
  );
}

function WorkflowCard({ workflow }: { workflow: Workflow }) {
  const updateWorkflow = useUpdateWorkflow();
  const addStatus = useAddStatus();
  const updateStatus = useUpdateStatus();
  const reorder = useReorderStatuses();
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [statusDraft, setStatusDraft] = useState("");
  const [newStatus, setNewStatus] = useState("");
  const [newFinal, setNewFinal] = useState(false);

  const pending = [updateWorkflow, addStatus, updateStatus, reorder].some((m) => m.isPending);
  const statuses = sortedStatuses(workflow);
  const callbacks = (after?: () => void) => ({
    onSuccess: () => {
      setError(null);
      after?.();
    },
    onError: (e: Error) => setError(e),
  });

  const move = (index: number, delta: number) => {
    const ids = statuses.map((s) => s.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    reorder.mutate({ workflowId: workflow.id, status_ids: ids }, callbacks());
  };

  const saveWorkflow = (event: FormEvent) => {
    event.preventDefault();
    updateWorkflow.mutate(
      { id: workflow.id, name: nameDraft.trim(), description: descriptionDraft.trim() },
      callbacks(() => setEditing(false)),
    );
  };

  const saveStatusName = (event: FormEvent, id: number) => {
    event.preventDefault();
    updateStatus.mutate({ id, name: statusDraft.trim() }, callbacks(() => setRenamingId(null)));
  };

  const submitNewStatus = (event: FormEvent) => {
    event.preventDefault();
    if (!newStatus.trim()) return setError(new Error("Укажите название статуса"));
    addStatus.mutate(
      { workflowId: workflow.id, name: newStatus.trim(), is_final: newFinal },
      callbacks(() => {
        setNewStatus("");
        setNewFinal(false);
      }),
    );
  };

  const titleId = `workflow-${workflow.id}-title`;
  return (
    <section className={workflow.is_active ? "panel workflow-card" : "panel workflow-card inactive"} aria-labelledby={titleId}>
      <div className="section-head">
        {editing ? (
          <form className="editor-form inline-form" onSubmit={saveWorkflow}>
            <label>
              Название процесса
              <input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} maxLength={200} />
            </label>
            <label>
              Описание
              <input value={descriptionDraft} onChange={(e) => setDescriptionDraft(e.target.value)} maxLength={2000} />
            </label>
            <div className="row-actions">
              <button className="primary" disabled={pending}>
                Сохранить
              </button>
              <button type="button" className="secondary" onClick={() => setEditing(false)}>
                Отмена
              </button>
            </div>
          </form>
        ) : (
          <div>
            <h2 id={titleId}>
              {workflow.name}{" "}
              {workflow.is_default && <span className="badge badge-3">Базовый</span>}{" "}
              {!workflow.is_active && <span className="badge badge-warning">Отключён</span>}
            </h2>
            {workflow.description && <p>{workflow.description}</p>}
          </div>
        )}
        {!editing && (
          <div className="row-actions">
            <button
              className="text-button"
              onClick={() => {
                setNameDraft(workflow.name);
                setDescriptionDraft(workflow.description);
                setEditing(true);
              }}
            >
              Переименовать
            </button>
            {workflow.is_default ? (
              <small className="field-hint">Базовый процесс нельзя отключить</small>
            ) : (
              <button
                className="text-button"
                disabled={pending}
                onClick={() =>
                  updateWorkflow.mutate({ id: workflow.id, is_active: !workflow.is_active }, callbacks())
                }
              >
                {workflow.is_active ? "Отключить процесс" : "Включить процесс"}
              </button>
            )}
          </div>
        )}
      </div>
      {error ? <ErrorAlert error={error} /> : null}
      <ol className="status-list" aria-label={`Статусы процесса «${workflow.name}»`}>
        {statuses.map((s, i) => (
          <li key={s.id} className={s.is_active ? "status-row" : "status-row inactive"}>
            <span className="status-position" aria-hidden="true">
              {i + 1}
            </span>
            {renamingId === s.id ? (
              <form className="editor-form inline-form status-name" onSubmit={(e) => saveStatusName(e, s.id)}>
                <label>
                  Новое название статуса «{s.name}»
                  <input value={statusDraft} onChange={(e) => setStatusDraft(e.target.value)} maxLength={120} />
                </label>
                <div className="row-actions">
                  <button className="primary" disabled={pending}>
                    Сохранить
                  </button>
                  <button type="button" className="secondary" onClick={() => setRenamingId(null)}>
                    Отмена
                  </button>
                </div>
              </form>
            ) : (
              <span className="status-name">
                {s.name} {s.is_final && <span className="badge badge-3">Финальный</span>}{" "}
                {!s.is_active && <span className="badge badge-warning">Отключён</span>}
              </span>
            )}
            <div className="row-actions status-actions">
              <button
                className="icon-button"
                aria-label={`Поднять статус «${s.name}»`}
                disabled={i === 0 || pending}
                onClick={() => move(i, -1)}
              >
                <ArrowUp size={16} />
              </button>
              <button
                className="icon-button"
                aria-label={`Опустить статус «${s.name}»`}
                disabled={i === statuses.length - 1 || pending}
                onClick={() => move(i, 1)}
              >
                <ArrowDown size={16} />
              </button>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={s.is_final}
                  disabled={pending}
                  onChange={(e) => updateStatus.mutate({ id: s.id, is_final: e.target.checked }, callbacks())}
                />
                Финальный<span className="visually-hidden"> статус «{s.name}»</span>
              </label>
              <button
                className="text-button"
                onClick={() => {
                  setStatusDraft(s.name);
                  setRenamingId(s.id);
                }}
              >
                Переименовать<span className="visually-hidden"> статус «{s.name}»</span>
              </button>
              <button
                className="text-button"
                disabled={pending}
                onClick={() => updateStatus.mutate({ id: s.id, is_active: !s.is_active }, callbacks())}
              >
                {s.is_active ? "Отключить" : "Включить"}
                <span className="visually-hidden"> статус «{s.name}»</span>
              </button>
            </div>
          </li>
        ))}
      </ol>
      <form className="editor-form add-status" onSubmit={submitNewStatus}>
        <label>
          Новый статус процесса «{workflow.name}»
          <input value={newStatus} onChange={(e) => setNewStatus(e.target.value)} maxLength={120} />
        </label>
        <label className="toggle">
          <input type="checkbox" checked={newFinal} onChange={(e) => setNewFinal(e.target.checked)} />
          Финальный
        </label>
        <button className="secondary" disabled={pending}>
          Добавить статус
        </button>
      </form>
    </section>
  );
}
