import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import { useLoginHistory, usePasswordPolicy, useSessions, useTerminateOthers, useTerminateSession } from "../../api/security";
import { formatDateTime } from "../../lib/format";
import { useAdminUsers, usePendingRegistrations, useResetUserPassword } from "../../api/admin";
import { useSession } from "../../app/AuthGate";
import { Modal } from "../../components/Modal";
import { Notice } from "../../components/Notice";
import { ErrorAlert, queryFallback, RefreshError } from "../../components/QueryState";
import type { SessionItem } from "../../api/security";
import { SettingsPanel } from "./SettingsPanel";
import { ROLES } from "../../lib/user";

const STATES = { active: "Активен", ended: "Завершён", expired: "Истёк" } as const;
const KEYCLOAK_REASONS: Record<string, string> = {
  disabled: "Журнал Keycloak недоступен: хранение событий не включено",
  not_configured: "Журнал Keycloak недоступен: интеграция с Keycloak не настроена",
  unavailable: "Журнал Keycloak сейчас недоступен, попробуйте позже",
};

export function SettingsSecurityPage() {
  const { user } = useSession();
  return (
    <>
      <SessionsPanel />
      <HistoryPanel />
      <PolicyPanel />
      {user.roles.includes(ROLES.superadmin) && <PasswordManager />}
    </>
  );
}

function SessionsPanel() {
  const sessions = useSessions();
  const terminate = useTerminateSession();
  const terminateOthers = useTerminateOthers();
  const [notice, setNotice] = useState("");
  // Ending a session signs that device out, so it is confirmed first, naming what ends.
  const [confirming, setConfirming] = useState<{ kind: "one"; session: SessionItem } | { kind: "others" } | null>(null);
  const error = terminate.error ?? terminateOthers.error;
  const hasOthers = (sessions.data ?? []).some((s) => !s.current);
  function confirmEnd() {
    if (!confirming) return;
    const done = { onSuccess: (r: { message: string }) => setNotice(r.message), onSettled: () => setConfirming(null) };
    if (confirming.kind === "one") terminate.mutate(confirming.session.id, done);
    else terminateOthers.mutate(undefined, done);
  }
  return (
    <SettingsPanel titleId="sessions-title" title="Мои сеансы" description="Устройства, на которых вы вошли в CRM. Завершённый сеанс потребует входа заново.">
      {sessions.isPending && <div className="loading" role="status">Загружаем сеансы…</div>}
      {sessions.isError && <ErrorAlert error={sessions.error} onRetry={() => void sessions.refetch()} />}
      <ul className="sender-queue">
        {sessions.data?.map((s) => (
          <li key={s.id}>
            <div>
              <strong>{s.device}</strong>{s.current && <> · <span className="muted">Это устройство</span></>}
              <div className="muted">IP {s.ip ?? "—"} · вход {formatDateTime(s.created_at)} · активность {formatDateTime(s.last_active_at)}</div>
            </div>
            {!s.current && (
              <button type="button" className="secondary" aria-label={`Завершить сеанс ${s.device}`} disabled={terminate.isPending}
                onClick={() => setConfirming({ kind: "one", session: s })}>Завершить</button>
            )}
          </li>
        ))}
      </ul>
      {hasOthers && (
        <button type="button" className="secondary" disabled={terminateOthers.isPending}
          onClick={() => setConfirming({ kind: "others" })}>Завершить все остальные</button>
      )}
      {notice && <Notice tone="info">{notice}</Notice>}
      {error && <Notice tone="error">{errorText(error)}</Notice>}
      {confirming && (
        <Modal title={confirming.kind === "one" ? "Завершить сеанс?" : "Завершить все остальные сеансы?"} close={() => setConfirming(null)}>
          <p className="form-note">
            {confirming.kind === "one"
              ? `Устройство «${confirming.session.device}» выйдет из CRM и потребует входа заново.`
              : "Все устройства, кроме этого, выйдут из CRM и потребуют входа заново."}
          </p>
          <div className="modal-actions">
            <button type="button" className="secondary" onClick={() => setConfirming(null)}>Отмена</button>
            <button type="button" className="primary" disabled={terminate.isPending || terminateOthers.isPending} onClick={confirmEnd}>
              {confirming.kind === "one" ? "Завершить сеанс" : "Завершить все остальные"}
            </button>
          </div>
        </Modal>
      )}
    </SettingsPanel>
  );
}

function HistoryPanel() {
  const history = useLoginHistory();
  const data = history.data;
  return (
    <SettingsPanel titleId="history-title" title="История входов" description="Входы в CRM за 30 дней и события журнала Keycloak.">
      {history.isPending && <div className="loading" role="status">Загружаем историю входов…</div>}
      {history.isError && <ErrorAlert error={history.error} onRetry={() => void history.refetch()} />}
      <h3>Входы в CRM (30 дней)</h3>
      {data?.crm.length === 0 && <p className="muted">Входов за 30 дней нет</p>}
      <ul className="sender-queue">
        {data?.crm.map((e, i) => (
          <li key={i}><span>{formatDateTime(e.at)} · {e.device} · IP {e.ip ?? "—"}</span><span className="muted">{STATES[e.state]}</span></li>
        ))}
      </ul>
      <h3>Журнал Keycloak</h3>
      {data && !data.keycloak.available && <p className="muted">{KEYCLOAK_REASONS[data.keycloak.reason ?? "unavailable"]}</p>}
      {data?.keycloak.available && data.keycloak.events.length === 0 && <p className="muted">Событий пока нет</p>}
      <ul className="sender-queue">
        {data?.keycloak.events.map((e, i) => (
          <li key={i}><span>{formatDateTime(e.at)} · <strong>{e.label}</strong></span><span className="muted">{e.ip}</span></li>
        ))}
      </ul>
    </SettingsPanel>
  );
}

function PolicyPanel() {
  const policy = usePasswordPolicy();
  const data = policy.data;
  return (
    <SettingsPanel titleId="policy-title" title="Парольная политика" description="Требования Keycloak к паролям сотрудников.">
      {policy.isPending && <div className="loading" role="status">Загружаем политику…</div>}
      {policy.isError && <ErrorAlert error={policy.error} onRetry={() => void policy.refetch()} />}
      {data && !data.available && <p className="muted">Политика сейчас недоступна: нет связи с Keycloak.</p>}
      {data?.available && (
        <ul>
          {data.rules.map((r) => <li key={r}>{r}</li>)}
          {data.brute_force && <li>{data.brute_force}</li>}
        </ul>
      )}
      {data && (
        <div className="wizard-actions">
          <a className="secondary" href={data.change_password_url} target="_blank" rel="noreferrer">Сменить пароль</a>
          {data.admin_console_url && (
            <a className="secondary" href={data.admin_console_url} target="_blank" rel="noreferrer">Изменить политику в Keycloak</a>
          )}
        </div>
      )}
      {data?.admin_console_url && <p className="muted">Политику меняет администратор в консоли Keycloak (нужна учётная запись администратора Keycloak).</p>}
    </SettingsPanel>
  );
}

function PasswordManager() {
  const users = useAdminUsers();
  const pending = usePendingRegistrations();
  const reset = useResetUserPassword();
  const accounts = [
    ...(users.data?.users ?? []).map((user) => ({ id: user.keycloak_id, label: `${user.username} — ${user.full_name}` })),
    ...(pending.data?.pending ?? []).map((user) => ({ id: user.keycloak_id, label: `${user.username} — ожидает назначения роли` })),
  ];

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const keycloakId = new FormData(event.currentTarget).get("user_id");
    if (typeof keycloakId !== "string" || !keycloakId) return;
    reset.reset();
    reset.mutate(keycloakId);
  }

  return (
    <SettingsPanel
      titleId="password-management-title"
      title="Управление паролями"
      description="Новый временный пароль потребуется передать сотруднику лично. Все его прежние сеансы завершатся."
    >
      {reset.error && <ErrorAlert error={reset.error} />}
      {queryFallback([users, pending]) ?? (
        <>
          <RefreshError queries={[users, pending]} />
          {!users.data?.available && !pending.data?.available && <p className="muted">Список учётных записей Keycloak сейчас недоступен.</p>}
          {accounts.length > 0 && (
            <form aria-label="Сброс пароля" onSubmit={submit}>
              <label>
                Учётная запись
                <select name="user_id" required defaultValue="">
                  <option value="" disabled>Выберите пользователя</option>
                  {accounts.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="wizard-actions">
                <button className="secondary" type="submit" disabled={reset.isPending}>
                  {reset.isPending ? "Сбрасываем…" : "Сбросить пароль"}
                </button>
              </div>
            </form>
          )}
        </>
      )}
      {reset.data && (
        <div className="banner-warning" role="status">
          <p>
            Временный пароль для <strong>{reset.data.username}</strong>: {" "}
            <code>{reset.data.temporary_password}</code>. Скопируйте его сейчас — повторно он не показывается.
          </p>
        </div>
      )}
    </SettingsPanel>
  );
}
