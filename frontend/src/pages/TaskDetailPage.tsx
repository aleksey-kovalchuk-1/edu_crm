import { Link, useParams } from "react-router";
import { ArrowLeft } from "lucide-react";
import { ApiError } from "../api/client";
import { useTask } from "../api/tasks";
import { paths, taskPath } from "../app/navigation";
import { RefreshError, queryFallback } from "../components/QueryState";
import { TaskActivity } from "../components/tasks/TaskActivity";
import { TaskChecklist } from "../components/tasks/TaskChecklist";
import { TaskComments } from "../components/tasks/TaskComments";
import { TaskInlineDescription, TaskInlineTitle } from "../components/tasks/TaskInlineText";
import { TaskSidebar } from "../components/tasks/TaskSidebar";
import { TaskStatusActions } from "../components/tasks/TaskStatusActions";
import { TaskSubtasks } from "../components/tasks/TaskSubtasks";

/**
 * Two columns, CRM-style: the work itself on the left (title, status actions, description, then
 * history → checklist → subtasks → comments, the order set in D-198), every property on the right,
 * each edited in place — no separate edit mode. On narrow screens the properties sit between the
 * title block and the rest, so the title is still the first thing on the page.
 */
export function TaskDetailPage() {
  const { id } = useParams();
  const taskId = Number(id);
  const task = useTask(taskId);

  if (task.error instanceof ApiError && task.error.status === 404) {
    return (
      <section className="panel">
        <div className="empty">
          <h2>Задача не найдена</h2>
          <p>Возможно, она архивирована или относится к вузу, который вам не назначен.</p>
          <Link className="text-button" to={paths.tasks}>
            К списку задач
          </Link>
        </div>
      </section>
    );
  }
  const fallback = queryFallback([task]);
  if (fallback || !task.data) return fallback;
  const t = task.data;

  return (
    <>
      <RefreshError queries={[task]} />
      <div className="detail-links">
        <Link className="back-link text-button" to={paths.tasks}>
          <ArrowLeft size={16} />
          К списку задач
        </Link>
        {t.parent && (
          <span className="muted">
            Подзадача: <Link to={taskPath(t.parent.id)}>{t.parent.title}</Link>
          </span>
        )}
      </div>
      <div className="task-detail">
        <section className="panel task-head">
          <TaskInlineTitle task={t} />
          <TaskStatusActions task={t} />
          <TaskInlineDescription task={t} />
        </section>
        <TaskSidebar task={t} />
        <div className="task-detail-rest">
          <section className="panel">
            <TaskActivity taskId={t.id} />
          </section>
          <section className="panel">
            <TaskChecklist taskId={t.id} items={t.checklist} />
          </section>
          {!t.parent && (
            <section className="panel">
              <TaskSubtasks taskId={t.id} />
            </section>
          )}
          <section className="panel">
            <TaskComments taskId={t.id} />
          </section>
        </div>
      </div>
    </>
  );
}
