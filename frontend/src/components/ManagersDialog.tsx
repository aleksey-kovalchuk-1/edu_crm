import { useState, type FormEvent } from "react";
import { useCrmUsers, useSetUniversityManagers } from "../api/catalogs";
import type { University } from "../api/types";
import { ROLES } from "../lib/user";
import { FormFooter } from "./forms/FormParts";
import { Modal } from "./Modal";

/** Supervisor/admin dialog replacing the full list of a university's managers. */
export function ManagersDialog({
  university,
  close,
}: {
  university: University;
  close: () => void;
}) {
  const users = useCrmUsers(ROLES.user);
  const save = useSetUniversityManagers();
  const [selected, setSelected] = useState<number[]>(
    university.managers.map((m) => m.id),
  );
  // Current managers stay listed even if they no longer appear among active crm-users.
  const options = (users.data ?? []).map((u) => ({
    id: u.id,
    full_name: u.full_name,
    email: u.email,
  }));
  for (const m of university.managers)
    if (!options.some((o) => o.id === m.id)) options.push({ ...m, email: "" });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const userIds = options.map((o) => o.id).filter((id) => selected.includes(id));
    save.mutate({ id: university.id, userIds }, { onSuccess: close });
  }

  return (
    <Modal title="Ответственные от ИТ-школы" close={close}>
      <form onSubmit={submit}>
        <p className="muted form-note">
          Отметьте менеджеров, ответственных за «{university.name}». Менеджер видит
          только назначенные ему учебные заведения. Пользователь появляется в списке
          после первого входа в CRM.
        </p>
        <fieldset className="checkbox-group">
          <legend>Менеджеры</legend>
          {users.isPending ? (
            <p className="muted">Загружаем пользователей…</p>
          ) : options.length ? (
            options.map((o) => (
              <label className="checkbox" key={o.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(o.id)}
                  onChange={(e) =>
                    setSelected((ids) =>
                      e.target.checked ? [...ids, o.id] : ids.filter((x) => x !== o.id),
                    )
                  }
                />
                <span>
                  {o.full_name}
                  {o.email && <small>{o.email}</small>}
                </span>
              </label>
            ))
          ) : (
            <p className="muted">Нет пользователей с ролью менеджера.</p>
          )}
        </fieldset>
        <FormFooter
          error={save.error ?? (users.data === undefined ? users.error : null)}
          pending={save.isPending}
          onCancel={close}
          submitLabel="Сохранить"
        />
      </form>
    </Modal>
  );
}
