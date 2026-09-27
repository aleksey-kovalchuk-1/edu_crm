import { errorText } from "../../api/client";
import { isStuck, useBackupStatus, useRequestBackup, type BackupFile, type BackupRun } from "../../api/backups";
import { useSession } from "../../app/AuthGate";
import { formatDateTime } from "../../lib/format";
import { ROLES } from "../../lib/user";

const REASONS: Record<string, string> = {
  not_configured: "Резервное копирование не подключено к этому серверу.",
  no_report: "Отчёт о резервном копировании пока не записан: служба копирования ещё не запускалась с этой версией.",
  damaged: "Отчёт о резервном копировании повреждён — проверьте журнал службы копирования на сервере.",
};
const ERRORS: Record<string, string> = {
  preflight_failed: "не прошла проверка настроек копирования",
  database_backup_failed: "не удалось создать копию базы данных",
  attachments_backup_failed: "не удалось создать копию вложений",
  verification_failed: "копия не прошла проверку расшифровкой",
  retention_failed: "не удалось удалить устаревшие копии",
};

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} МБ`;
  return `${(bytes / 1024 ** 3).toFixed(1)} ГБ`;
}

function runResult(run: BackupRun) {
  if (run.result === "running") return "Выполняется";
  if (run.result === "interrupted") return "Прервана (нет итогового отчёта)";
  if (run.result === "failure") return `Ошибка: ${ERRORS[run.error ?? ""] ?? "копия не создана"}`;
  return "Успешно";
}

function FileCell({ file }: { file: BackupFile | null }) {
  return file ? <td>{formatSize(file.size_bytes)}</td> : <td className="danger">нет файла</td>;
}

/** Only crm-superadmin; the page never lists paths, offers downloads, restores or deletions. */
export function SettingsBackupsPage() {
  const { user } = useSession();
  const allowed = user.roles.includes(ROLES.superadmin);
  const status = useBackupStatus(allowed);
  const request = useRequestBackup();

  if (!allowed) {
    return <section className="panel"><p className="muted">Раздел доступен только суперадминистратору.</p></section>;
  }
  if (status.isError) {
    return <section className="panel"><p className="danger" role="alert">{errorText(status.error)}</p></section>;
  }
  const data = status.data;
  if (!data) return <section className="panel"><p className="muted">Загрузка…</p></section>;

  const running = data.last_run?.result === "running";
  const busy = data.pending_request || running || request.isPending;

  return (
    <>
      <section className="panel" aria-labelledby="backup-state-title">
        <h2 id="backup-state-title">Резервное копирование</h2>
        <p className="muted">Зашифрованные копии базы данных и вложений создаются на сервере ежедневно в 03:30.</p>
        {!data.available && <p className="muted" role="status">{REASONS[data.reason ?? "no_report"]}</p>}
        {data.available && data.stale && (
          <p className="danger" role="alert">Последняя успешная копия старше 36 часов — проверьте службу копирования.</p>
        )}
        {data.last_run && (
          <dl className="organization-details">
            <div><dt>Последний запуск</dt><dd>{formatDateTime(data.last_run.started_at)} · {data.last_run.trigger === "manual" ? "вручную" : "по расписанию"}</dd></div>
            <div><dt>Результат</dt><dd className={data.last_run.result === "success" ? "text-green" : undefined}>{runResult(data.last_run)}</dd></div>
            {data.last_run.verified !== null && (
              <div><dt>Проверка</dt><dd>{data.last_run.verified ? "Проверена расшифровкой" : "Проверка не пройдена"}</dd></div>
            )}
            <div><dt>Последняя успешная копия</dt><dd>{data.last_success_at ? formatDateTime(data.last_success_at) : "нет"}</dd></div>
            {data.retention && (
              <div><dt>Хранение</dt><dd>
                {data.retention.verification_configured
                  ? `ежедневные копии — ${data.retention.days} дней, не меньше ${data.retention.min_pairs} последних; ручные не удаляются`
                  : "автоматическое удаление выключено: не настроен ключ проверки"}
              </dd></div>
            )}
          </dl>
        )}
        <div className="wizard-actions">
          <button type="button" className="primary" disabled={busy || data.reason === "not_configured"} onClick={() => request.mutate()}>
            Создать копию сейчас
          </button>
        </div>
        {data.pending_request && !running && (isStuck(data) ? (
          <p role="alert" className="danger">
            Служба копирования не отвечает: запрос ждёт больше 5 минут. Проверьте агент копирования на сервере.
          </p>
        ) : (
          <p role="status" className="muted">Копия запрошена — служба копирования начнёт её в течение минуты.</p>
        ))}
        {running && <p role="status" className="muted">Выполняется создание копии…</p>}
        {request.isError && <p className="danger" role="alert">{errorText(request.error)}</p>}
      </section>

      {data.available && (
        <section className="panel" aria-labelledby="backup-list-title">
          <h2 id="backup-list-title">Копии</h2>
          {data.pairs.length === 0 ? <p className="muted">Копий пока нет.</p> : (
            <table className="data-table">
              <thead><tr><th>Копия</th><th>Создана</th><th>База данных</th><th>Вложения</th></tr></thead>
              <tbody>
                {data.pairs.map((pair) => (
                  <tr key={pair.label}>
                    <td>{pair.label.startsWith("manual-") ? "Ручная" : "Ежедневная"}</td>
                    <td>{pair.database ?? pair.attachments ? formatDateTime((pair.database ?? pair.attachments)!.created_at) : "—"}</td>
                    <FileCell file={pair.database} />
                    <FileCell file={pair.attachments} />
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </>
  );
}
