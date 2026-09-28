import type { FormEvent } from "react";
import { CheckCircle2 } from "lucide-react";
import { useChangeUserRole, usePendingRegistrations, type AssignableRole } from "../../api/admin";
import { AdminUsersPanel } from "../../components/AdminUsersPanel";
import { ErrorAlert, queryFallback, RefreshError } from "../../components/QueryState";
import { Notice } from "../../components/Notice";
import { CreateAccountPanel } from "./CreateAccountPanel";
import { SettingsPanel } from "./SettingsPanel";

/**
 * A "pending registration" is a Keycloak account that can already sign in but has no CRM role
 * yet — Irina may grant either the manager or administrator role.
 */
function PendingRegistrations() {
  const pending = usePendingRegistrations();
  const changeRole = useChangeUserRole();
  const data = pending.data;

  function grantAccess(event: FormEvent<HTMLFormElement>, keycloakId: string) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("role");
    if (value !== "crm-user" && value !== "crm-admin") return;
    changeRole.mutate({ keycloakId, role: value as AssignableRole });
  }

  return (
    <SettingsPanel
      titleId="pending-registrations-title"
      title="Заявки на доступ"
      description="Учётные записи Keycloak, у которых пока нет ни одной роли CRM."
    >
      {changeRole.error && <ErrorAlert error={changeRole.error} />}
      {queryFallback([pending]) ??
        (data && (
          <>
            <RefreshError queries={[pending]} />
            {!data.available && (
              <Notice tone="info">
                Keycloak Admin API не настроен в этом окружении — заявки на доступ недоступны.
              </Notice>
            )}
            {data.available && data.pending.length === 0 && (
              <p className="empty">Заявок на доступ нет.</p>
            )}
            {data.available && data.pending.length > 0 && (
              <div className="table-wrap">
                <table className="data-table stack-table users-table">
                  <thead>
                    <tr>
                      <th scope="col">Логин</th>
                      <th scope="col">Имя пользователя Keycloak</th>
                      <th scope="col">
                        <span className="visually-hidden">Действия</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pending.map((p) => (
                      <tr key={p.keycloak_id}>
                        <td data-label="Логин">
                          <strong className="cell-title wrap-anywhere">{p.email}</strong>
                        </td>
                        <td data-label="Имя пользователя Keycloak" className="muted wrap-anywhere">{p.username}</td>
                        <td data-label="Доступ" className="role-editor-cell">
                          <form className="role-editor" aria-label={`Доступ пользователя ${p.username}`} onSubmit={(event) => grantAccess(event, p.keycloak_id)}>
                            <label>
                              Роль
                              <select name="role" defaultValue="crm-user">
                                <option value="crm-user">КАМ</option>
                                <option value="crm-admin">Администратор</option>
                              </select>
                            </label>
                            <button type="submit" className="secondary" disabled={changeRole.isPending}>
                              <CheckCircle2 size={16} />
                              Выдать доступ
                            </button>
                          </form>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ))}
    </SettingsPanel>
  );
}

export function SettingsUsersPage() {
  return (
    <>
      <CreateAccountPanel />
      <PendingRegistrations />
      <AdminUsersPanel editable />
    </>
  );
}
