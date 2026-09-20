import { useState } from "react";
import { errorText } from "../../api/client";
import {
  TASK_STATUS_LABELS,
  useBulkArchive,
  useBulkDeadline,
  useBulkStatus,
  type BulkResult,
  type TaskStatus,
} from "../../api/tasks";
import { Modal } from "../Modal";

const ALL_STATUSES = Object.keys(TASK_STATUS_LABELS) as TaskStatus[];

function ResultBanner({ result }: { result: BulkResult }) {
  if (!result.skipped.length) return null;
  return (
    <p className="danger" role="alert">
      Не удалось изменить {result.skipped.length} из {result.updated.length + result.skipped.length}:{" "}
      {result.skipped.map((s) => `#${s.id} (${s.reason})`).join(", ")}
    </p>
  );
}

export function TaskBulkActionsBar({ selectedIds, onDone }: { selectedIds: number[]; onDone: () => void }) {
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const bulkStatus = useBulkStatus();
  const bulkDeadline = useBulkDeadline();
  const bulkArchive = useBulkArchive();
  const lastResult = bulkStatus.data ?? bulkDeadline.data ?? bulkArchive.data;
  const lastError = bulkStatus.error ?? bulkDeadline.error ?? bulkArchive.error;

  return (
    <div className="bulk-actions-bar">
      <span>{selectedIds.length} выбрано</span>
      <label className="inline-select">
        Статус
        <select
          defaultValue=""
          onChange={(e) => {
            const to_status = e.target.value as TaskStatus;
            if (!to_status) return;
            // Selection stays after status/deadline changes (so the skip summary below stays visible
            // and a second action can be applied to the same selection); only archiving clears it.
            bulkStatus.mutate({ task_ids: selectedIds, to_status });
            e.target.value = "";
          }}
        >
          <option value="" disabled>
            Изменить статус…
          </option>
          {ALL_STATUSES.map((s) => (
            <option value={s} key={s}>
              {TASK_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </label>
      <label className="inline-select">
        Срок
        <input
          type="date"
          aria-label="Новый срок для выбранных задач"
          onChange={(e) => bulkDeadline.mutate({ task_ids: selectedIds, deadline: e.target.value || null })}
        />
      </label>
      <button type="button" className="secondary danger" onClick={() => setConfirmingArchive(true)}>
        Архивировать
      </button>
      {lastError && <p className="danger" role="alert">{errorText(lastError)}</p>}
      {lastResult && <ResultBanner result={lastResult} />}
      {confirmingArchive && (
        <Modal title="Архивировать задачи" close={() => setConfirmingArchive(false)}>
          <p>
            Архивировать {selectedIds.length} {selectedIds.length === 1 ? "задачу" : "задач"}? Их можно будет
            восстановить позже.
          </p>
          <div className="modal-actions">
            <button type="button" className="secondary" onClick={() => setConfirmingArchive(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="primary"
              disabled={bulkArchive.isPending}
              onClick={() =>
                bulkArchive.mutate(
                  { task_ids: selectedIds, confirm: true },
                  {
                    onSuccess: () => {
                      setConfirmingArchive(false);
                      onDone();
                    },
                  },
                )
              }
            >
              Архивировать
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
