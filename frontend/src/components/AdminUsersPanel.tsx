import { useAdminUsers } from "../api/admin";
import { formatDateTime } from "../lib/format";
import { queryFallback, RefreshError } from "./QueryState";

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
export function AdminUsersPanel() {
  const users = useAdminUsers();
  const list = users.data?.users;

  return (
    <section className="panel" aria-labelledby="admin-users-title">
      <div className="section-head">
        <div>
          <h2 id="admin-users-title">Пользователи CRM</h2>
          <p>{users.data ? `Всего: ${users.data.total}` : "Учётные записи и роли."}</p>
        </div>
      </div>
      {queryFallback([users]) ??
        (list && (
          <>
            <RefreshError queries={[users]} />
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Логин</th>
                    <th scope="col">Имя</th>
                    <th scope="col">Роли</th>
                    <th scope="col">Статус</th>
                    <th scope="col">Последний вход</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <strong className="cell-title">{u.email}</strong>
                      </td>
                      <td>{u.full_name}</td>
                      <td>{u.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ") || <span className="muted">—</span>}</td>
                      <td>{u.is_active ? "Активен" : "Отключён"}</td>
                      <td className="muted">
                        {u.last_login_at ? formatDateTime(u.last_login_at) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!list.length && <p className="empty">Пользователи не найдены.</p>}
            </div>
          </>
        ))}
    </section>
  );
}
