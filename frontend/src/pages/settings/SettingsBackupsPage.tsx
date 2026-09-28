import { isStale, isStuck, useBackupRun, useBackupStatus, useRequestBackup, type BackupItem, type LastBackupRun } from "../../api/backups";
import { errorText } from "../../api/client";
import { useSession } from "../../app/AuthGate";
import { Notice, type NoticeTone } from "../../components/Notice";
import { formatDateTime } from "../../lib/format";
import { ROLES } from "../../lib/user";
import { SettingsPanel } from "./SettingsPanel";

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
      <span className={item.verified ? "badge badge-3" : "badge badge-4"}>
        {item.verified ? "Проверена" : "Сохранена, без проверки"}
      </span>
    </li>
  );
}

export function SettingsBackupsPage() {
  const { user } = useSession();
  if (!user.roles.includes(ROLES.superadmin)) {
    return <section className="panel settings-panel"><Notice tone="warning">Нет доступа к резервному копированию.</Notice></section>;
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

const RUN_TONES: Record<LastBackupRun["result"], NoticeTone> = {
  success: "success", running: "info", failure: "error", interrupted: "error",
};

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
      {stale && <Notice tone="warning">Последняя копия старше 36 часов — проверьте службу копирования на сервере.</Notice>}
      {run?.last_run && (
        <Notice tone={RUN_TONES[run.last_run.result] ?? "info"} role="status">
          {runText(run.last_run)}
        </Notice>
      )}
      {run?.reason === "unavailable" && <Notice tone="info">Сведения о последнем запуске сейчас недоступны.</Notice>}
      {run?.manual_available && (
        <div className="wizard-actions">
          <button type="button" className="primary" disabled={busy} onClick={() => request.mutate()}>Создать копию сейчас</button>
        </div>
      )}
      {run?.pending_request && !running && (isStuck(run) ? (
        <Notice tone="error">Служба копирования не отвечает: запрос ждёт больше 5 минут. Проверьте агент копирования на сервере.</Notice>
      ) : (
        <Notice tone="info">Копия запрошена — служба копирования начнёт её в течение минуты.</Notice>
      ))}
      {request.isError && <Notice tone="error">{errorText(request.error)}</Notice>}
    </>
  );
}

function BackupStatusPanel() {
  const query = useBackupStatus();
  const status = query.data;
  const newest = status?.available ? (status.backups[0]?.created_at ?? null) : undefined;
  return (
    <SettingsPanel
      titleId="backup-status-title"
      title="Состояние резервных копий"
      description="Сохраняются зашифрованные копии базы данных и вложений. Ключ восстановления и сами архивы хранятся вне CRM."
    >
      <BackupRunPanel newest={newest} />
      {query.isPending && <div className="loading" role="status">Загружаем сведения о копиях…</div>}
      {query.isError && <Notice tone="error">{errorText(query.error)}</Notice>}
      {status && !status.available && (
        <Notice tone="info">{status.reason === "unavailable"
          ? "Сведения о резервных копиях сейчас недоступны."
          : "Сведения о резервных копиях пока не поступили с сервера."}</Notice>
      )}
      {status?.available && status.backups.length === 0 && <Notice tone="info">Сохранённых пар копий пока нет.</Notice>}
      {status?.available && status.backups.length > 0 && (
        <>
          <h3>Последние копии</h3>
          <ul className="sender-queue" aria-label="Последние резервные копии">
            {status.backups.map((item) => <BackupRow key={`${item.source}-${item.created_at}`} item={item} />)}
          </ul>
          <p className="muted">«Проверена» означает, что архивы удалось расшифровать и прочитать. Это не заменяет проверку восстановления системы.</p>
        </>
      )}
    </SettingsPanel>
  );
}
