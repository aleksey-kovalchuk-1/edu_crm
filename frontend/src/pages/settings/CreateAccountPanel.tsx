import { SettingsPanel } from "./SettingsPanel";
import type { FormEvent } from "react";
import { useCreateAccount, type NewAccount } from "../../api/admin";
import { ErrorAlert } from "../../components/QueryState";
import { FieldError } from "../../components/forms/FormParts";

export function CreateAccountPanel() {
  const create = useCreateAccount();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const data: NewAccount = {
      username: String(values.get("username") ?? "").trim(),
      email: String(values.get("email") ?? "").trim(),
      first_name: String(values.get("first_name") ?? "").trim(),
      last_name: String(values.get("last_name") ?? "").trim(),
      role: values.get("role") === "crm-admin" ? "crm-admin" : "crm-user",
    };
    create.reset();
    create.mutate(data, { onSuccess: () => form.reset() });
  }

  return (
    <SettingsPanel
      titleId="create-account-title"
      title="Новая учётная запись"
      description="Создайте менеджера или администратора. Пароль потребуется передать сотруднику лично."
    >
      <form aria-label="Новая учётная запись" onSubmit={submit}>
        <div className="form-row">
          <label>
            Логин
            <input name="username" required minLength={3} maxLength={40} pattern="[a-z][a-z0-9._-]+" autoComplete="off" />
            <FieldError error={create.error} field="username" />
          </label>
          <label>
            Электронная почта
            <input name="email" type="email" required maxLength={254} autoComplete="off" />
            <FieldError error={create.error} field="email" />
          </label>
        </div>
        <div className="form-row">
          <label>
            Имя
            <input name="first_name" required maxLength={100} autoComplete="off" />
            <FieldError error={create.error} field="first_name" />
          </label>
          <label>
            Фамилия
            <input name="last_name" required maxLength={100} autoComplete="off" />
            <FieldError error={create.error} field="last_name" />
          </label>
        </div>
        <label>
          Роль
          <select name="role" defaultValue="crm-user">
            <option value="crm-user">КАМ</option>
            <option value="crm-admin">Администратор</option>
          </select>
        </label>
        {create.error && <ErrorAlert error={create.error} />}
        <div className="wizard-actions">
          <button className="primary" type="submit" disabled={create.isPending}>
            {create.isPending ? "Создаём…" : "Создать пользователя"}
          </button>
        </div>
      </form>
      {create.data && (
        <div className="banner-warning" role="status">
          <p>
            Учётная запись <strong>{create.data.username}</strong> создана. Временный пароль:
            {" "}<code>{create.data.temporary_password}</code>. Скопируйте его сейчас — повторно он не показывается.
          </p>
        </div>
      )}
    </SettingsPanel>
  );
}
