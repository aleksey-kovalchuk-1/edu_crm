import { useBackupStatus, type BackupItem } from "../../api/backups";
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

function BackupStatusPanel() {
  const query = useBackupStatus();
  const status = query.data;
  return (
    <section className="panel" aria-labelledby="backup-status-title">
      <h2 id="backup-status-title">Состояние резервных копий</h2>
      <p className="muted">Сохраняются зашифрованные копии базы данных и вложений. Ключ восстановления и сами архивы хранятся вне CRM.</p>
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
