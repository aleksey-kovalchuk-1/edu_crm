import type { FormEvent } from "react";
import { useAdminUsers, useChangeUserRole, type AdminUser, type AssignableRole } from "../api/admin";
import { formatDateTime } from "../lib/format";
import { roleLabel } from "../lib/user";
import { SettingsPanel } from "../pages/settings/SettingsPanel";
import { Notice } from "./Notice";
import { ErrorAlert, queryFallback, RefreshError } from "./QueryState";

const PROTECTED = new Set(["crm-supervisor", "crm-superadmin"]);

/**
 * Superadmin-only account directory (GET /admin/users): total count and every user's login.
 * Shared by Настройки → Аккаунт (quick glance) and Настройки → Пользователи и роли (full page).
 * One short label per user — the highest CRM role — never a list of inherited roles.
 */
export function AdminUsersPanel({ editable = false }: { editable?: boolean }) {
  const users = useAdminUsers();
  const change = useChangeUserRole();
  const list = users.data?.users;

  function saveRole(event: FormEvent<HTMLFormElement>, user: AdminUser) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("role");
    if (value !== "crm-user" && value !== "crm-admin") return;
    change.mutate({ keycloakId: user.keycloak_id, role: value as AssignableRole });
  }

  return (
    <SettingsPanel
      titleId="admin-users-title"
      title="Пользователи CRM"
      description={users.data?.available ? `Всего: ${users.data.total}` : "Учётные записи и роли."}
    >
      {change.error && <ErrorAlert error={change.error} />}
      {change.data && <Notice tone="success">Роль пользователя {change.data.username} изменена.</Notice>}
      {queryFallback([users]) ??
        (list && (
          <>
            <RefreshError queries={[users]} />
            {!users.data?.available && <Notice tone="info">Список учётных записей сейчас недоступен.</Notice>}
            {users.data?.available && (
              <div className="table-wrap">
                <table className="data-table stack-table users-table">
                  <thead>
                    <tr>
                      <th scope="col">Пользователь</th>
                      <th scope="col">Роль</th>
                      <th scope="col">Статус</th>
                      <th scope="col">Последний вход</th>
                      {editable && <th scope="col">Изменить роль</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((u) => (
                      <tr key={u.keycloak_id}>
                        <td data-label="Пользователь">
                          <strong className="cell-title wrap-anywhere">{u.username}</strong>
                          {u.full_name && <span className="user-name">{u.full_name}</span>}
                          <span className="user-email wrap-anywhere">{u.email}</span>
                        </td>
                        <td data-label="Роль">{roleLabel(u.roles) ?? <span className="muted">—</span>}</td>
                        <td data-label="Статус">{u.is_active ? "Активен" : "Отключён"}</td>
                        <td data-label="Последний вход" className="muted">{u.last_login_at ? formatDateTime(u.last_login_at) : "—"}</td>
                        {editable && (
                          <td data-label="Изменить роль" className="role-editor-cell">
                            {u.roles.some((role) => PROTECTED.has(role)) ? (
                              <span className="muted">Защищённая роль</span>
                            ) : (
                              <form className="role-editor" aria-label={`Роль пользователя ${u.username}`} onSubmit={(event) => saveRole(event, u)}>
                                <label>
                                  <span className="visually-hidden">Новая роль</span>
                                  <select name="role" defaultValue={u.roles.includes("crm-admin") ? "crm-admin" : "crm-user"}>
                                    <option value="crm-user">КАМ</option>
                                    <option value="crm-admin">Администратор</option>
                                  </select>
                                </label>
                                <button type="submit" className="secondary" disabled={change.isPending}>Сохранить роль</button>
                              </form>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!list.length && <p className="empty">Пользователи не найдены.</p>}
              </div>
            )}
          </>
        ))}
    </SettingsPanel>
  );
}
