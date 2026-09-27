import type { FormEvent } from "react";
import { useAdminUsers, usePendingRegistrations, useResetUserPassword } from "../../api/admin";
import { useSession } from "../../app/AuthGate";
import { ErrorAlert, queryFallback, RefreshError } from "../../components/QueryState";
import { ROLES } from "../../lib/user";

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
    <section className="panel" aria-labelledby="password-management-title">
      <div className="section-head">
        <div>
          <h2 id="password-management-title">Управление паролями</h2>
          <p>Новый временный пароль потребуется передать сотруднику лично. Все его прежние сеансы завершатся.</p>
        </div>
      </div>
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
    </section>
  );
}

export function SettingsSecurityPage() {
  const { user } = useSession();
  if (!user.roles.includes(ROLES.superadmin)) {
    return (
      <section className="panel">
        <h2>Безопасность</h2>
        <p>Управление паролями сотрудников доступно только главному администратору.</p>
      </section>
    );
  }
  return <PasswordManager />;
}
