import { CheckCircle2 } from "lucide-react";
import { useApprovePendingRegistration, usePendingRegistrations } from "../../api/admin";
import { AdminUsersPanel } from "../../components/AdminUsersPanel";
import { ErrorAlert, queryFallback, RefreshError } from "../../components/QueryState";

/**
 * A "pending registration" is a Keycloak account that can already sign in but has no CRM role
 * yet — approving one grants the single baseline `crm-user` role (D-214/D-215, docs/api/admin.md).
 */
function PendingRegistrations() {
  const pending = usePendingRegistrations();
  const approve = useApprovePendingRegistration();
  const data = pending.data;

  return (
    <section className="panel" aria-labelledby="pending-registrations-title">
      <div className="section-head">
        <div>
          <h2 id="pending-registrations-title">Заявки на доступ</h2>
          <p>Учётные записи Keycloak, у которых пока нет ни одной роли CRM.</p>
        </div>
      </div>
      {approve.error && <ErrorAlert error={approve.error} />}
      {queryFallback([pending]) ??
        (data && (
          <>
            <RefreshError queries={[pending]} />
            {!data.available && (
              <p className="muted">
                Keycloak Admin API не настроен в этом окружении — заявки на доступ недоступны.
              </p>
            )}
            {data.available && data.pending.length === 0 && (
              <p className="empty">Заявок на доступ нет.</p>
            )}
            {data.available && data.pending.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
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
                        <td>
                          <strong className="cell-title">{p.email}</strong>
                        </td>
                        <td className="muted">{p.username}</td>
                        <td className="row-actions">
                          <button
                            type="button"
                            className="secondary"
                            disabled={approve.isPending}
                            onClick={() => approve.mutate(p.keycloak_id)}
                          >
                            <CheckCircle2 size={16} />
                            Одобрить
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ))}
    </section>
  );
}

export function SettingsUsersPage() {
  return (
    <>
      <PendingRegistrations />
      <AdminUsersPanel />
    </>
  );
}
