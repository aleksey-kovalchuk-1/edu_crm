import { isStale, isStuck, useBackupRun, useBackupStatus, useRequestBackup, type BackupItem, type LastBackupRun } from "../../api/backups";
import { errorText } from "../../api/client";
import { useSession } from "../../app/AuthGate";
import { formatDateTime } from "../../lib/format";
import { ROLES } from "../../lib/user";

function kind(source: string): string {
  if (source.startsWith("daily-")) return "Ежедневная копия";
  if (source.startsWith("manual-")) return "Ручная копия";
  return "Перед публикацией";
}

function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} МБ`;
  return `${Math.ceil(bytes / 1024)} КБ`;
}

function BackupRow({ item }: { item: BackupItem }) {
  return (
    <li>
      <div>
        <strong>{kind(item.source)}</strong>
        <div className="muted">{formatDateTime(item.created_at)} · база {size(item.database_bytes)} · вложения {size(item.attachments_bytes)}</div>
      </div>
      <span className={item.verified ? "text-green" : "muted"}>
        {item.verified ? "Проверена" : "Сохранена, без проверки"}
      </span>
    </li>
  );
}

export function SettingsBackupsPage() {
  const { user } = useSession();
  if (!user.roles.includes(ROLES.superadmin)) {
    return <section className="panel"><p role="alert">Нет доступа к резервному копированию.</p></section>;
  }
  return <BackupStatusPanel />;
}

const RUN_ERRORS: Record<string, string> = {
  preflight_failed: "не прошла проверка настроек копирования",
  database_backup_failed: "не удалось создать копию базы данных",
  attachments_backup_failed: "не удалось создать копию вложений",
  verification_failed: "копия не прошла проверку расшифровкой",
  retention_failed: "не удалось удалить устаревшие копии",
  status_record_failed: "копия создана, но сведения о ней не записаны",
};

function runText(run: LastBackupRun): string {
  const how = run.trigger === "manual" ? "ручной" : "по расписанию";
  if (run.result === "running") return `Выполняется запуск ${how} с ${formatDateTime(run.started_at)}`;
  if (run.result === "interrupted") return `Последний запуск ${how} прерван: итог не записан`;
  if (run.result === "failure") return `Последний запуск завершился ошибкой: ${RUN_ERRORS[run.error ?? ""] ?? "копия не создана"}`;
  return `Последний запуск ${how} успешен: ${formatDateTime(run.finished_at ?? run.started_at)}`;
}

/** Latest run, stale warning and the manual request (added beside the pair history below). */
function BackupRunPanel({ newest }: { newest: string | null | undefined }) {
  const runQuery = useBackupRun();
  const request = useRequestBackup();
  const run = runQuery.data;
  const running = run?.last_run?.result === "running";
  const busy = Boolean(run?.pending_request || running || request.isPending);
  const stale = newest !== undefined && isStale(newest);
  return (
    <>
      {stale && <p className="danger" role="alert">Последняя копия старше 36 часов — проверьте службу копирования на сервере.</p>}
      {run?.last_run && (
        <p role="status" className={run.last_run.result === "failure" || run.last_run.result === "interrupted" ? "danger" : "muted"}>
          {runText(run.last_run)}
        </p>
      )}
      {run?.reason === "unavailable" && <p className="muted">Сведения о последнем запуске сейчас недоступны.</p>}
      {run?.manual_available && (
        <div className="wizard-actions">
          <button type="button" className="primary" disabled={busy} onClick={() => request.mutate()}>Создать копию сейчас</button>
        </div>
      )}
      {run?.pending_request && !running && (isStuck(run) ? (
        <p role="alert" className="danger">Служба копирования не отвечает: запрос ждёт больше 5 минут. Проверьте агент копирования на сервере.</p>
      ) : (
        <p role="status" className="muted">Копия запрошена — служба копирования начнёт её в течение минуты.</p>
      ))}
      {request.isError && <p className="danger" role="alert">{errorText(request.error)}</p>}
    </>
  );
}

function BackupStatusPanel() {
  const query = useBackupStatus();
  const status = query.data;
  const newest = status?.available ? (status.backups[0]?.created_at ?? null) : undefined;
  return (
    <section className="panel" aria-labelledby="backup-status-title">
      <h2 id="backup-status-title">Состояние резервных копий</h2>
      <p className="muted">Сохраняются зашифрованные копии базы данных и вложений. Ключ восстановления и сами архивы хранятся вне CRM.</p>
      <BackupRunPanel newest={newest} />
      {query.isPending && <p>Загрузка…</p>}
      {query.isError && <p className="danger" role="alert">{errorText(query.error)}</p>}
      {status && !status.available && (
        <p role="status">{status.reason === "unavailable"
          ? "Сведения о резервных копиях сейчас недоступны."
          : "Сведения о резервных копиях пока не поступили с сервера."}</p>
      )}
      {status?.available && status.backups.length === 0 && <p role="status">Сохранённых пар копий пока нет.</p>}
      {status?.available && status.backups.length > 0 && (
        <>
          <h3>Последние копии</h3>
          <ul className="sender-queue" aria-label="Последние резервные копии">
            {status.backups.map((item) => <BackupRow key={`${item.source}-${item.created_at}`} item={item} />)}
          </ul>
          <p className="muted">«Проверена» означает, что архивы удалось расшифровать и прочитать. Это не заменяет проверку восстановления системы.</p>
        </>
      )}
    </section>
  );
}
