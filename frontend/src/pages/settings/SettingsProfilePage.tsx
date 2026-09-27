import { useMemo, useState, type FormEvent } from "react";
import { ApiError, errorText } from "../../api/client";
import { contactStatus, useProfile, useUpdateProfile, type Profile } from "../../api/profile";
import { PhoneVerificationPanel } from "./PhoneVerificationPanel";
import { SenderAddressPanel } from "./SenderAddressPanel";

const TIME_ZONES: string[] =
  typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["Europe/Moscow"];

type Form = Pick<Profile, "first_name" | "middle_name" | "last_name" | "timezone" | "telegram" | "whatsapp">;
const FIELD_KEYS = ["first_name", "middle_name", "last_name", "timezone", "telegram", "whatsapp"] as const;

export function SettingsProfilePage() {
  const profile = useProfile();
  if (profile.isError) {
    return <section className="panel"><p className="danger" role="alert">{errorText(profile.error)}</p></section>;
  }
  if (!profile.data) {
    return <section className="panel"><p className="muted">Загрузка…</p></section>;
  }
  return (
    <>
      <PersonalDataForm profile={profile.data} />
      <PhoneVerificationPanel />
      <SenderAddressPanel />
    </>
  );
}

function PersonalDataForm({ profile }: { profile: Profile }) {
  const update = useUpdateProfile();
  const [form, setForm] = useState<Form>(() => ({
    first_name: profile.first_name, middle_name: profile.middle_name, last_name: profile.last_name,
    timezone: profile.timezone, telegram: profile.telegram, whatsapp: profile.whatsapp,
  }));
  const [saved, setSaved] = useState(false);
  const zones = useMemo(
    () => (TIME_ZONES.includes(form.timezone) ? TIME_ZONES : [form.timezone, ...TIME_ZONES]),
    [form.timezone],
  );

  const error = update.error;
  const fieldError = (field: string) => (error instanceof ApiError ? error.fieldMessage(field) : undefined);
  const hasFieldError = FIELD_KEYS.some((key) => fieldError(key));

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    update.mutate(form, {
      onSuccess: (saved) => {
        // Show what the server stored (e.g. "@anna" → "anna", "8 (999)…" → "+7999…").
        setForm({
          first_name: saved.first_name, middle_name: saved.middle_name, last_name: saved.last_name,
          timezone: saved.timezone, telegram: saved.telegram, whatsapp: saved.whatsapp,
        });
        setSaved(true);
      },
    });
  }

  function field(key: (typeof FIELD_KEYS)[number], label: string, props: Record<string, unknown> = {}) {
    const message = fieldError(key);
    return (
      <label>
        {label}
        <input value={form[key]} onChange={(e) => set(key, e.target.value)}
          aria-invalid={message ? true : undefined} {...props} />
        {message && <small className="field-error danger">{message}</small>}
      </label>
    );
  }

  return (
    <form className="panel" onSubmit={submit} aria-labelledby="profile-personal-title" noValidate>
      <div className="section-head">
        <div>
          <h2 id="profile-personal-title">Личные данные</h2>
          <p>Имя, отчество и фамилия сохраняются в учётной записи для входа.</p>
        </div>
      </div>
      <div className="wizard-body">
        <div className="form-row">
          {field("first_name", "Имя", { maxLength: 100, autoComplete: "given-name" })}
          {field("middle_name", "Отчество", { maxLength: 100, autoComplete: "additional-name" })}
          {field("last_name", "Фамилия", { maxLength: 100, autoComplete: "family-name" })}
        </div>
        <label>
          Email
          <input value={profile.email} readOnly aria-readonly="true" />
          <small className="field-hint">Меняется администратором в учётной записи.</small>
        </label>
        <label>
          Часовой пояс
          <select value={form.timezone} onChange={(e) => set("timezone", e.target.value)}
            aria-invalid={fieldError("timezone") ? true : undefined}>
            {zones.map((zone) => <option key={zone} value={zone}>{zone.replace(/_/g, " ")}</option>)}
          </select>
          {fieldError("timezone") && <small className="field-error danger">{fieldError("timezone")}</small>}
        </label>
        <div className="form-row">
          <div>
            {field("telegram", "Telegram", { maxLength: 40, placeholder: "@username" })}
            {/* Status of the SAVED value: typing a handle does not make it saved. */}
            <small className="field-hint">{contactStatus(profile.telegram)}</small>
          </div>
          <div>
            {field("whatsapp", "WhatsApp", { maxLength: 32, type: "tel", placeholder: "+7XXXXXXXXXX" })}
            <small className="field-hint">{contactStatus(profile.whatsapp)}</small>
          </div>
        </div>
        <small className="field-hint">
          Контакты только сохраняются в профиле: CRM не отправляет сообщения в мессенджеры.
        </small>

        {error && !hasFieldError && <p className="danger" role="alert">{errorText(error)}</p>}
        {saved && <p className="text-green" role="status">Изменения сохранены</p>}
        <div className="wizard-actions">
          <button className="primary" disabled={update.isPending}>{update.isPending ? "Сохраняем…" : "Сохранить"}</button>
        </div>
      </div>
    </form>
  );
}
