import { useState, type FormEvent } from "react";
import {
  useAdminUsers,
  useChangeUserRole,
  useRemoveUserRole,
  useSendPasswordSetup,
  type AdminUser,
  type AssignableRole,
} from "../api/admin";
import { formatDateTime } from "../lib/format";
import { roleLabel } from "../lib/user";
import { SettingsPanel } from "../pages/settings/SettingsPanel";
import { Modal } from "./Modal";
import { Notice } from "./Notice";
import { ErrorAlert, queryFallback, RefreshError } from "./QueryState";

const PROTECTED = new Set(["crm-supervisor", "crm-superadmin"]);

/**
 * «Изменить роль» for a KAM or administrator: opens the role picker with «Сохранить» and «Удалить роль»
 * (owner request 29 Sep). Removing asks for confirmation, because the person loses CRM access at once.
 */
function RoleEditor({
  user,
  pending,
  onSave,
  onRemove,
}: {
  user: AdminUser;
  pending: boolean;
  onSave: (role: AssignableRole) => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <button type="button" className="secondary" aria-label={`Изменить роль пользователя ${user.username}`} onClick={() => setOpen(true)}>
        Изменить роль
      </button>
    );
  }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("role");
    if (value !== "crm-user" && value !== "crm-admin") return;
    onSave(value);
    setOpen(false);
  }
  return (
    <form className="role-editor" aria-label={`Роль пользователя ${user.username}`} onSubmit={save}>
      <label>
        <span className="visually-hidden">Новая роль</span>
        <select name="role" defaultValue={user.roles.includes("crm-admin") ? "crm-admin" : "crm-user"} autoFocus>
          <option value="crm-user">КАМ</option>
          <option value="crm-admin">Администратор</option>
        </select>
      </label>
      <div className="role-editor-actions">
        <button type="submit" className="primary" disabled={pending}>Сохранить</button>
        <button type="button" className="secondary danger" disabled={pending} onClick={onRemove}>Удалить роль</button>
        <button type="button" className="text-button" onClick={() => setOpen(false)}>Отмена</button>
      </div>
    </form>
  );
}

/**
 * Superadmin-only account directory (GET /admin/users): total count and every user's login.
 * Shared by Настройки → Аккаунт (quick glance) and Настройки → Пользователи и роли (full page).
 * One short label per user — the highest CRM role — never a list of inherited roles.
 */
export function AdminUsersPanel({ editable = false }: { editable?: boolean }) {
  const users = useAdminUsers();
  const change = useChangeUserRole();
  const remove = useRemoveUserRole();
  const setup = useSendPasswordSetup();
  const [confirming, setConfirming] = useState<AdminUser | null>(null);
  const list = users.data?.users;
  const busy = change.isPending || remove.isPending;

  function removeRole(user: AdminUser) {
    remove.mutate({ keycloakId: user.keycloak_id, username: user.username }, { onSettled: () => setConfirming(null) });
  }

  return (
    <SettingsPanel
      titleId="admin-users-title"
      title="Пользователи CRM"
      description={users.data?.available ? `Всего: ${users.data.total}` : "Учётные записи и роли."}
    >
      {change.error && <ErrorAlert error={change.error} />}
      {remove.error && <ErrorAlert error={remove.error} />}
      {setup.error && <ErrorAlert error={setup.error} />}
      {change.data && <Notice tone="success">Роль пользователя {change.data.username} изменена.</Notice>}
      {remove.isSuccess && (
        <Notice tone="success">Роль пользователя {remove.variables?.username} удалена, доступ к CRM прекращён.</Notice>
      )}
      {setup.data && <Notice tone="success">{setup.data.message}</Notice>}
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
                        <td data-label="Статус">
                          {u.is_active ? "Активен" : "Отключён"}
                          {u.setup_pending && (
                            <span className="user-setup">
                              <span className="badge badge-warning">Не задал пароль</span>
                              {editable && (
                                <button
                                  type="button"
                                  className="text-button"
                                  aria-label={`Отправить письмо для установки пароля пользователю ${u.username}`}
                                  disabled={setup.isPending}
                                  onClick={() => setup.mutate(u.keycloak_id)}
                                >
                                  Отправить письмо для пароля
                                </button>
                              )}
                            </span>
                          )}
                        </td>
                        <td data-label="Последний вход" className="muted">{u.last_login_at ? formatDateTime(u.last_login_at) : "—"}</td>
                        {editable && (
                          <td data-label="Изменить роль" className="role-editor-cell">
                            {u.roles.some((role) => PROTECTED.has(role)) ? (
                              <span className="muted">Защищённая роль</span>
                            ) : (
                              <RoleEditor
                                user={u}
                                pending={busy}
                                onSave={(role) => change.mutate({ keycloakId: u.keycloak_id, role })}
                                onRemove={() => setConfirming(u)}
                              />
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
      {confirming && (
        <Modal title="Удалить роль?" close={() => setConfirming(null)}>
          <p>
            Пользователь <strong>{confirming.username}</strong> ({roleLabel(confirming.roles)}) потеряет доступ к CRM сразу,
            его сеансы завершатся. Учётная запись останется и вернётся в «Заявки на доступ».
          </p>
          <div className="modal-actions">
            <button type="button" className="secondary" onClick={() => setConfirming(null)}>Отмена</button>
            <button type="button" className="primary danger" disabled={remove.isPending} onClick={() => removeRole(confirming)}>
              {remove.isPending ? "Удаляем…" : "Удалить роль"}
            </button>
          </div>
        </Modal>
      )}
    </SettingsPanel>
  );
}
