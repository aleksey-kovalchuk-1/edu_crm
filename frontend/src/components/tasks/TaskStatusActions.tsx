import { useState } from "react";
import { NEEDS_COMMENT, NEXT_STATUSES, TRANSITION_LABELS, useChangeTaskStatus, type Task, type TaskStatus } from "../../api/tasks";
import { errorText } from "../../api/client";
import { StatusCommentModal } from "./StatusCommentModal";

export function TaskStatusActions({ task }: { task: Task }) {
  const [pendingComment, setPendingComment] = useState<TaskStatus | null>(null);
  const change = useChangeTaskStatus(task.id);
  const options = NEXT_STATUSES[task.status] ?? [];
  if (!options.length) return null;

  function go(to: TaskStatus, comment = "") {
    change.mutate({ to_status: to, comment, version: task.version });
  }

  return (
    <div className="task-status-actions">
      {options.map((to) => {
        const label = TRANSITION_LABELS[task.status]?.[to] ?? to;
        const key = `${task.status}:${to}`;
        return (
          <button
            key={to}
            type="button"
            className={to === "cancelled" ? "secondary danger" : "secondary"}
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
