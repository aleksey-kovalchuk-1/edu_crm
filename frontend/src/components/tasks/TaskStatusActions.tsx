import { useState } from "react";
import { NEEDS_COMMENT, NEXT_STATUSES, TRANSITION_LABELS, useChangeTaskStatus, type Task, type TaskStatus } from "../../api/tasks";
import { errorText } from "../../api/client";
import { StatusCommentModal } from "./StatusCommentModal";

/** The one move that pushes the task forward from each status — shown as the primary button. */
function primaryTarget(task: Task): TaskStatus | null {
  switch (task.status) {
    case "new":
      return "in_progress";
    case "in_progress":
      return task.approval_required ? "awaiting_review" : "completed";
    case "awaiting_review":
      return "completed";
    case "deferred":
      return "in_progress";
    default:
      return null;
  }
}

export function TaskStatusActions({ task }: { task: Task }) {
  const [pendingComment, setPendingComment] = useState<TaskStatus | null>(null);
  const change = useChangeTaskStatus(task.id);
  const options = NEXT_STATUSES[task.status] ?? [];
  if (!options.length) return null;
  const primary = primaryTarget(task);
  const ordered = primary && options.includes(primary) ? [primary, ...options.filter((o) => o !== primary)] : options;

  function go(to: TaskStatus, comment = "") {
    change.mutate({ to_status: to, comment, version: task.version });
  }

  return (
    <div className="task-status-actions">
      {ordered.map((to) => {
        const label = TRANSITION_LABELS[task.status]?.[to] ?? to;
        const key = `${task.status}:${to}`;
        const className = to === primary ? "primary" : to === "cancelled" ? "secondary danger" : "secondary";
        return (
          <button
            key={to}
            type="button"
            className={className}
            disabled={change.isPending}
            onClick={() => (NEEDS_COMMENT.has(key) ? setPendingComment(to) : go(to))}
          >
            {label}
          </button>
        );
      })}
      {change.isError && <p className="danger" role="alert">{errorText(change.error)}</p>}
      {pendingComment && (
        <StatusCommentModal
          pending={change.isPending}
          error={change.error}
          onCancel={() => setPendingComment(null)}
          onSubmit={(comment) => {
            go(pendingComment, comment);
            setPendingComment(null);
          }}
        />
      )}
    </div>
  );
}
