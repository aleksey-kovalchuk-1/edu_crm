import { useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Columns3, Plus, RefreshCw } from "lucide-react";
import { useLaunchTasks } from "../api/launchTasks";
import { useLaunches } from "../api/queries";
import { TASK_STATUS_LABELS } from "../api/tasks";
import {
  currentStatus,
  launchWorkflow,
  useStatusChanges,
  useWorkflows,
} from "../api/workflows";
import { paths, taskPath } from "../app/navigation";
import { Modal } from "../components/Modal";
import { ErrorAlert, RefreshError, queryFallback } from "../components/QueryState";
import { StatusChangeDialog } from "../components/StatusChangeDialog";
import { StatusTimeline } from "../components/StatusTimeline";
import { TaskCreateForm } from "../components/forms/TaskCreateForm";
import { formatDate, launchCode } from "../lib/format";

export function LaunchPage() {
  const { id } = useParams();
  const launchId = Number(id);
  const launches = useLaunches();
  const workflows = useWorkflows();
  const changes = useStatusChanges(launchId);
  const launchTasks = useLaunchTasks(launchId);
  const [changing, setChanging] = useState(false);
  const [creating, setCreating] = useState(false);
  const queries = [launches, workflows];
  const fallback = queryFallback(queries);
  if (fallback || !launches.data || !workflows.data) return fallback;

  const launch = launches.data.find((l) => l.id === launchId);
  if (!launch) {
    return (
      <section className="panel">
        <div className="empty">
          <h2>Взаимодействие не найдено</h2>
          <p>Возможно, оно удалено или относится к вузу, который вам не назначен.</p>
          <Link className="text-button" to={paths.interactions}>
            К списку взаимодействий
          </Link>
        </div>
      </section>
    );
  }
  const workflow = launchWorkflow(workflows.data, launch);
  const status = currentStatus(workflow, launch);

  return (
    <>
      <RefreshError queries={queries} />
      <div className="detail-links">
        <Link className="back-link text-button" to={paths.interactions}>
          <ArrowLeft size={16} />
          Все взаимодействия
        </Link>
        <Link className="text-button" to={paths.statusBoard}>
          <Columns3 size={16} />
          Доска статусов
        </Link>
      </div>
      <section className="panel launch-summary">
        <div className="section-head">
          <div>
            <p className="card-id">{launchCode(launch.id)}</p>
            <h2>{launch.program}</h2>
            <p>
              {launch.university}
              {launch.city ? `, ${launch.city}` : ""}
            </p>
          </div>
          <div className="row-actions">
            <button className="secondary" onClick={() => setCreating(true)}>
              <Plus size={17} />
              Создать задачу
            </button>
            <button className="primary" onClick={() => setChanging(true)} disabled={!workflow}>
              <RefreshCw size={17} />
              Сменить статус
            </button>
          </div>
        </div>
        <dl className="fields">
          <div>
            <dt>Текущий статус</dt>
            <dd>
              <span className="badge" data-testid="current-status">
                {status?.name ?? "Не указан"}
              </span>
            </dd>
          </div>
          <div>
            <dt>Процесс</dt>
            <dd>{workflow?.name ?? "—"}</dd>
          </div>
          <div>
            <dt>ИТ-продукт</dt>
            <dd>{launch.product}</dd>
          </div>
          <div>
            <dt>Ответственный</dt>
            <dd>{launch.owner}</dd>
          </div>
          <div>
            <dt>Обучающиеся</dt>
            <dd>{launch.students}</dd>
          </div>
          <div>
            <dt>Плановый запуск</dt>
            <dd className={launch.overdue ? "danger" : undefined}>{formatDate(launch.deadline)}</dd>
          </div>
        </dl>
      </section>
      <section className="panel">
        <div className="section-head">
          <h2>История взаимодействия</h2>
        </div>
        <div className="timeline-wrap">
          {changes.isError && (
            <ErrorAlert error={changes.error} onRetry={() => void changes.refetch()} />
          )}
          {changes.isPending && !changes.isError && <div className="loading">Загружаем историю…</div>}
          {changes.data && <StatusTimeline changes={changes.data} />}
        </div>
      </section>
      {launchTasks.data && (
        <section className="panel">
          <h2>Связанные задачи</h2>
          {launchTasks.data.categories.map((c) => (
            <div key={c.index} className="launch-task-category">
              <h3>
                {c.name}
                {c.index === launchTasks.data!.current_category && <span className="badge">текущий этап</span>}
                {c.unfinished_count > 0 && <span className="badge badge-warning">{c.unfinished_count} незаверш.</span>}
              </h3>
              {c.tasks.length === 0 ? (
                <p className="muted">Нет задач</p>
              ) : (
                <ul>
                  {c.tasks.map((t) => (
                    <li key={t.id}>
                      <Link to={taskPath(t.id)}>{t.title}</Link>
                      {" — "}{TASK_STATUS_LABELS[t.status]}
                      {t.assignee && ` · ${t.assignee.full_name}`}
                      {t.deadline && ` · ${formatDate(t.deadline)}`}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {launchTasks.data.uncategorized.length > 0 && (
            <div className="launch-task-category">
              <h3>Без категории</h3>
              <ul>
                {launchTasks.data.uncategorized.map((t) => (
                  <li key={t.id}><Link to={taskPath(t.id)}>{t.title}</Link></li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
      {changing && workflow && (
        <StatusChangeDialog
          launch={launch}
          workflow={workflow}
          currentStatusId={status?.id}
          close={() => setChanging(false)}
        />
      )}
      {creating && (
        <Modal title="Новая задача" close={() => setCreating(false)}>
          <TaskCreateForm
            initialUniversityId={launch.university_id}
            initialLaunchId={launch.id}
            onCreated={() => setCreating(false)}
            onCancel={() => setCreating(false)}
          />
        </Modal>
      )}
    </>
  );
}
