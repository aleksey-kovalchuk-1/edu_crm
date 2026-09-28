import { useState, type FormEvent } from "react";
import { ApiError, errorText } from "../../api/client";
import {
  useOrganization, useUpdateOrganization, type Organization, type OrganizationInput,
} from "../../api/organization";
import { ErrorSummary } from "../../components/ErrorSummary";
import { Notice } from "../../components/Notice";
import { ErrorAlert } from "../../components/QueryState";
import { SettingsPanel } from "./SettingsPanel";

const fieldId = (key: string) => `organization-${key}`;

const FIELDS: { key: keyof OrganizationInput; label: string; long?: boolean; type?: string }[] = [
  { key: "name", label: "Название" },
  { key: "legal_name", label: "Полное наименование", long: true },
  { key: "ogrn", label: "ОГРН" },
  { key: "registration_date", label: "Дата регистрации", type: "date" },
  { key: "legal_address", label: "Юридический адрес", long: true },
  { key: "postal_address", label: "Почтовый адрес", long: true },
  { key: "contact_address", label: "Контактный адрес", long: true },
  { key: "phone", label: "Телефон", type: "tel" },
  { key: "email", label: "Email", type: "email" },
];

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}.${m}.${y}` : iso;
}

function toInput(org: Organization): OrganizationInput {
  return {
    name: org.name, legal_name: org.legal_name, ogrn: org.ogrn, registration_date: org.registration_date,
    legal_address: org.legal_address, postal_address: org.postal_address, contact_address: org.contact_address,
    phone: org.phone_display || org.phone, email: org.email,
  };
}

/** Настройки → Организация: read-only for everyone, editable for crm-admin / crm-superadmin. */
export function OrganizationCard({ canEdit }: { canEdit: boolean }) {
  const organization = useOrganization();
  if (organization.isError) {
    return <section className="panel settings-panel"><ErrorAlert error={organization.error} onRetry={() => void organization.refetch()} /></section>;
  }
  if (!organization.data) {
    return <section className="panel settings-panel"><div className="loading" role="status">Загружаем сведения об организации…</div></section>;
  }
  return canEdit ? <OrganizationForm organization={organization.data} /> : <OrganizationView organization={organization.data} />;
}

function OrganizationView({ organization }: { organization: Organization }) {
  const value = (key: keyof OrganizationInput) =>
    key === "phone" ? organization.phone_display : key === "registration_date" ? formatDate(organization.registration_date) : organization[key];
  return (
    <SettingsPanel titleId="organization-title" title="Организация" description="Реквизиты и контакты. Изменяет администратор.">
      <dl className="organization-details">
        {FIELDS.map((f) => (
          <div key={f.key}>
            <dt>{f.label}</dt>
            <dd>{value(f.key)}</dd>
          </div>
        ))}
      </dl>
    </SettingsPanel>
  );
}

function OrganizationForm({ organization }: { organization: Organization }) {
  const update = useUpdateOrganization();
  const [form, setForm] = useState<OrganizationInput>(() => toInput(organization));
  const [saved, setSaved] = useState(false);
  const error = update.error;
  const fieldError = (field: string) => (error instanceof ApiError ? error.fieldMessage(field) : undefined);
  const hasFieldError = FIELDS.some((f) => fieldError(f.key));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    update.mutate(form, {
      onSuccess: (result) => {
        setForm(toInput(result));
        setSaved(true);
      },
    });
  }

  return (
    <SettingsPanel
      titleId="organization-title"
      title="Организация"
      description="Реквизиты и контакты организации; сохраняются одним действием."
      onSubmit={submit}
    >
        <ErrorSummary errors={FIELDS.flatMap((f) => {
          const message = fieldError(f.key);
          return message ? [{ id: fieldId(f.key), label: f.label, message }] : [];
        })} />
        {FIELDS.map((f) => {
          const message = fieldError(f.key);
          return (
            <label key={f.key}>
              {f.label}
              <input
                id={fieldId(f.key)}
                type={f.type ?? "text"}
                value={form[f.key]}
                maxLength={f.long ? 500 : 200}
                aria-invalid={message ? true : undefined}
                onChange={(e) => { setForm((c) => ({ ...c, [f.key]: e.target.value })); setSaved(false); }}
              />
              {message && <small className="field-error danger">{message}</small>}
            </label>
          );
        })}
        {error && !hasFieldError && <Notice tone="error">{errorText(error)}</Notice>}
        {saved && <Notice tone="success">Изменения сохранены</Notice>}
        <div className="wizard-actions">
          <button className="primary" disabled={update.isPending}>{update.isPending ? "Сохраняем…" : "Сохранить"}</button>
        </div>
    </SettingsPanel>
  );
}
