import { useState, type FormEvent } from "react";
import { ApiError, errorText } from "../../api/client";
import {
  useOrganization, useUpdateOrganization, type Organization, type OrganizationInput,
} from "../../api/organization";

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
    return <section className="panel"><p className="danger" role="alert">{errorText(organization.error)}</p></section>;
  }
  if (!organization.data) {
    return <section className="panel"><p className="muted">Загрузка…</p></section>;
  }
  return canEdit ? <OrganizationForm organization={organization.data} /> : <OrganizationView organization={organization.data} />;
}

function OrganizationView({ organization }: { organization: Organization }) {
  const value = (key: keyof OrganizationInput) =>
    key === "phone" ? organization.phone_display : key === "registration_date" ? formatDate(organization.registration_date) : organization[key];
  return (
    <section className="panel" aria-labelledby="organization-title">
      <h2 id="organization-title">Организация</h2>
      <dl className="organization-details">
        {FIELDS.map((f) => (
          <div key={f.key}>
            <dt>{f.label}</dt>
            <dd>{value(f.key)}</dd>
          </div>
        ))}
      </dl>
    </section>
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
    <form className="panel" onSubmit={submit} aria-labelledby="organization-title" noValidate>
      <h2 id="organization-title">Организация</h2>
      <div className="wizard-body">
        {FIELDS.map((f) => {
          const message = fieldError(f.key);
          return (
            <label key={f.key}>
              {f.label}
              <input
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
        {error && !hasFieldError && <p className="danger" role="alert">{errorText(error)}</p>}
        {saved && <p className="text-green" role="status">Изменения сохранены</p>}
        <div className="wizard-actions">
          <button className="primary" disabled={update.isPending}>{update.isPending ? "Сохраняем…" : "Сохранить"}</button>
        </div>
      </div>
    </form>
  );
}
