import { useState } from "react";
import { errorText } from "../api/client";
import {
  useChangeStage,
  useLaunchHistory,
  useLaunches,
  useStages,
} from "../api/queries";
import { formatDate, formatDateTime } from "../lib/format";
import { Modal } from "./Modal";

export function LaunchDetailModal({
  id,
  close,
}: {
  id: number;
  close: () => void;
}) {
  const launches = useLaunches();
  const stages = useStages();
  const history = useLaunchHistory(id);
  const change = useChangeStage();
  const launch = launches.data?.find((l) => l.id === id);
  const [stageDraft, setStageDraft] = useState(launch?.stage ?? 0);
  if (!launch) return null;
  const stageNames = stages.data ?? [];
  const error = change.error ?? history.error ?? stages.error;

  return (
    <Modal title={launch.program} close={close}>
      <p className="subtitle">{launch.university}</p>
      <div className="detail-grid">
        <div>
          <small>ИТ-продукт</small>
          <strong>{launch.product}</strong>
        </div>
        <div>
          <small>Ответственный</small>
          <strong>{launch.owner}</strong>
        </div>
        <div>
          <small>Обучающиеся</small>
          <strong>{launch.students}</strong>
        </div>
        <div>
          <small>Плановый запуск</small>
          <strong>{formatDate(launch.deadline)}</strong>
        </div>
      </div>
      <label>
        Текущий этап
        <select
          value={stageDraft}
          onChange={(e) => setStageDraft(Number(e.target.value))}
        >
          {stageNames.map((s, i) => (
            <option key={s} value={i}>
              {i + 1}. {s}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">
        В шаблоне можно выбрать любой этап, включая возврат на доработку.
        Изменение сохраняется в истории.
      </p>
      <div className="modal-actions">
        <button
          className="primary"
          disabled={change.isPending || stageDraft === launch.stage}
          onClick={() =>
            change.mutate({ id, stage: stageDraft }, { onSuccess: close })
          }
        >
          Сохранить этап
        </button>
      </div>
      {error && (
        <p className="danger" role="alert">
          {errorText(error)}
        </p>
      )}
      <h3>История этапов</h3>
      <div className="history">
        {history.data?.map((h) => (
          <div key={h.id}>
            <i className="dot purple" />
            <span>
              {stageNames[h.stage]}
              <small>{formatDateTime(h.created_at)}</small>
            </span>
          </div>
        ))}
      </div>
    </Modal>
  );
}
