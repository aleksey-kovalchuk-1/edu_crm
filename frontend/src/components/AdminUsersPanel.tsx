import type { FormEvent } from "react";
import { useAdminUsers, useChangeUserRole, type AdminUser, type AssignableRole } from "../api/admin";
import { formatDateTime } from "../lib/format";
import { ErrorAlert, queryFallback, RefreshError } from "./QueryState";

const ROLE_LABELS: Record<string, string> = {
  "crm-user": "Менеджер",
  "crm-supervisor": "Руководитель",
  "crm-admin": "Администратор",
  "crm-superadmin": "Суперадминистратор",
};

/**
 * Superadmin-only account directory (GET /admin/users): total count and every user's login.
 * Shared by Настройки → Аккаунт (quick glance) and Настройки → Пользователи и роли (full page).
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
    <section className="panel" aria-labelledby="admin-users-title">
      <div className="section-head">
        <div>
          <h2 id="admin-users-title">Пользователи CRM</h2>
          <p>{users.data?.available ? `Всего: ${users.data.total}` : "Учётные записи и роли."}</p>
        </div>
      </div>
      {change.error && <ErrorAlert error={change.error} />}
      {change.data && <p role="status">Роль пользователя {change.data.username} изменена.</p>}
      {queryFallback([users]) ??
        (list && (
          <>
            <RefreshError queries={[users]} />
            {!users.data?.available && <p className="muted">Список учётных записей Keycloak сейчас недоступен.</p>}
            {users.data?.available && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Логин</th>
                      <th scope="col">Почта</th>
                      <th scope="col">Имя</th>
                      <th scope="col">Роли</th>
                      <th scope="col">Статус</th>
                      <th scope="col">Последний вход</th>
                      {editable && <th scope="col">Изменить роль</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((u) => (
                      <tr key={u.keycloak_id}>
                        <td><strong className="cell-title">{u.username}</strong></td>
                        <td>{u.email}</td>
                        <td>{u.full_name}</td>
                        <td>{u.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ") || <span className="muted">—</span>}</td>
                        <td>{u.is_active ? "Активен" : "Отключён"}</td>
                        <td className="muted">{u.last_login_at ? formatDateTime(u.last_login_at) : "—"}</td>
                        {editable && (
                          <td>
                            {u.roles.some((role) => role === "crm-supervisor" || role === "crm-superadmin") ? (
                              <span className="muted">Защищённая роль</span>
                            ) : (
                              <form aria-label={`Роль пользователя ${u.username}`} onSubmit={(event) => saveRole(event, u)}>
                                <label>
                                  Новая роль
                                  <select name="role" defaultValue={u.roles.includes("crm-admin") ? "crm-admin" : "crm-user"}>
                                    <option value="crm-user">Менеджер</option>
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
    </section>
  );
}
