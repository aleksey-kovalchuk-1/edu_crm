import { useState, type FormEvent } from "react";
import { useItProducts } from "../api/catalogs";
import {
  useSaveVendorCompany, useSaveVendorContact, useVendorCompanies, useVendorContacts,
  type VendorCompany, type VendorContact,
} from "../api/customerData";
import { useSession } from "../app/AuthGate";
import { Modal } from "../components/Modal";
import { ErrorAlert, queryFallback } from "../components/QueryState";
import { canEditCatalog } from "../lib/user";
import { useDebouncedValue } from "../lib/useDebouncedValue";

export function VendorsPage() {
  const { user } = useSession();
  const editable = canEditCatalog(user.roles);
  const [search, setSearch] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [productId, setProductId] = useState("");
  const [inactive, setInactive] = useState(false);
  const [companyForm, setCompanyForm] = useState<VendorCompany | "new" | null>(null);
  const [contactForm, setContactForm] = useState<VendorContact | "new" | null>(null);
  const q = useDebouncedValue(search);
  const companies = useVendorCompanies(q, inactive);
  const contacts = useVendorContacts(companyId ? Number(companyId) : undefined,
    productId ? Number(productId) : undefined, q, inactive);
  const products = useItProducts({ include_inactive: inactive });
  const saveCompany = useSaveVendorCompany();
  const saveContact = useSaveVendorContact();
  const selected = companies.data?.find((item) => item.id === Number(companyId));
  const selectedProducts = products.data?.filter((item) => item.company_id === selected?.id) ?? [];

  return <div className="customer-workspace">
    <div className="customer-toolbar">
      <label>Поиск <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Компания или контакт" /></label>
      <label>Компания <select value={companyId} onChange={(event) => { setCompanyId(event.target.value); setProductId(""); }}>
        <option value="">Все компании</option>
        {companies.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <label>Продукт <select value={productId} onChange={(event) => setProductId(event.target.value)}>
        <option value="">Все продукты</option>
        {products.data?.filter((item) => !companyId || item.company_id === Number(companyId))
          .map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <label className="customer-check"><input type="checkbox" checked={inactive} onChange={(event) => setInactive(event.target.checked)} /> Показать неактивные</label>
    </div>
    {saveCompany.error ? <ErrorAlert error={saveCompany.error} /> : null}
    {saveContact.error ? <ErrorAlert error={saveContact.error} /> : null}
    {queryFallback([companies, contacts, products]) ?? <div className="customer-grid">
      <section className="panel">
        <div className="section-head"><h2>Компании</h2>{editable ? <button className="primary" onClick={() => setCompanyForm("new")}>Добавить компанию</button> : null}</div>
        {companies.data?.length ? <ul className="customer-list">
          {companies.data.map((item) => <li key={item.id}>
            <button className="text-button" onClick={() => setCompanyId(String(item.id))}>{item.name}</button>
            {!item.is_active ? <span className="badge badge-4">Неактивно</span> : null}
            {editable ? <><button className="text-button" onClick={() => setCompanyForm(item)}>Изменить</button>
              <button className="text-button" onClick={() => saveCompany.mutate({ id: item.id, data: { is_active: !item.is_active } })}>
                {item.is_active ? "Деактивировать" : "Активировать"}</button></> : null}
          </li>)}
        </ul> : <p className="empty">Компании не найдены.</p>}
        {selected ? <div className="customer-related"><h3>Продукты компании</h3>
          {selectedProducts.length ? <ul>{selectedProducts.map((item) => <li key={item.id}>{item.name}</li>)}</ul> : <p className="muted">Продуктов пока нет.</p>}
        </div> : null}
      </section>
      <section className="panel">
        <div className="section-head"><h2>Контакты по продуктам</h2>{editable ? <button className="primary" onClick={() => setContactForm("new")}>Добавить контакт</button> : null}</div>
        {contacts.data?.length ? <div className="table-wrap"><table className="data-table"><thead><tr>
          <th scope="col">Контакт</th><th scope="col">Связь</th><th scope="col">Продукты</th><th scope="col">Статус</th>{editable ? <th scope="col">Действия</th> : null}
        </tr></thead><tbody>{contacts.data.map((item) => <tr key={item.id}>
          <td><strong className="cell-title">{item.full_name}</strong><small>{companies.data?.find((company) => company.id === item.company_id)?.name}</small></td>
          <td>{item.email || item.phone || "—"}<small>{item.preferred_channels.join(", ") || "Способ не указан"}</small></td>
          <td>{item.product_ids.map((id) => products.data?.find((product) => product.id === id)?.name ?? id).join(", ")}</td>
          <td>{item.is_active ? "Активно" : "Неактивно"}</td>
          {editable ? <td><button className="text-button" onClick={() => setContactForm(item)}>Изменить</button>{" "}
            <button className="text-button" onClick={() => saveContact.mutate({ id: item.id, data: { is_active: !item.is_active } })}>
              {item.is_active ? "Деактивировать" : "Активировать"}</button></td> : null}
        </tr>)}</tbody></table></div> : <p className="empty">Контактов не найдено.</p>}
      </section>
    </div>}
    {companyForm ? <Modal title={companyForm === "new" ? "Новая компания" : "Изменить компанию"} close={() => setCompanyForm(null)}>
      <CompanyEditor record={companyForm === "new" ? undefined : companyForm} save={saveCompany.mutateAsync} done={() => setCompanyForm(null)} />
    </Modal> : null}
    {contactForm ? <Modal title={contactForm === "new" ? "Новый контакт" : "Изменить контакт"} close={() => setContactForm(null)} wide>
      <ContactEditor record={contactForm === "new" ? undefined : contactForm} companies={companies.data ?? []}
        products={products.data ?? []} initialCompanyId={companyId ? Number(companyId) : undefined}
        save={saveContact.mutateAsync} done={() => setContactForm(null)} />
    </Modal> : null}
  </div>;
}

function CompanyEditor({ record, save, done }: {
  record?: VendorCompany; save: (args: { id?: number; data: Partial<VendorCompany> }) => Promise<VendorCompany>; done: () => void;
}) {
  const [name, setName] = useState(record?.name ?? "");
  const [error, setError] = useState<unknown>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try { await save({ id: record?.id, data: { name } }); done(); } catch (cause) { setError(cause); }
  }
  return <form onSubmit={submit} className="customer-form">
    <label>Название компании <input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label>
    {error ? <ErrorAlert error={error} /> : null}
    <div className="modal-actions"><button className="primary" type="submit">Сохранить</button></div>
  </form>;
}

function ContactEditor({ record, companies, products, initialCompanyId, save, done }: {
  record?: VendorContact; companies: VendorCompany[];
  products: { id: number; name: string; company_id?: number | null }[]; initialCompanyId?: number;
  save: (args: { id?: number; data: Partial<VendorContact> }) => Promise<VendorContact>; done: () => void;
}) {
  const [companyId, setCompanyId] = useState(record?.company_id ?? initialCompanyId ?? companies[0]?.id ?? 0);
  const [name, setName] = useState(record?.full_name ?? "");
  const [phone, setPhone] = useState(record?.phone ?? "");
  const [email, setEmail] = useState(record?.email ?? "");
  const [channels, setChannels] = useState(record?.preferred_channels.join("; ") ?? "");
  const [productIds, setProductIds] = useState(record?.product_ids ?? []);
  const [error, setError] = useState<unknown>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await save({ id: record?.id, data: {
        ...(record ? {} : { company_id: companyId }), full_name: name, phone, email,
        preferred_channels: channels.split(/[;,\n]/).map((value) => value.trim()).filter(Boolean), product_ids: productIds,
      } });
      done();
    } catch (cause) { setError(cause); }
  }
  return <form onSubmit={submit} className="customer-form">
    <div className="form-row"><label>Компания <select value={companyId} disabled={!!record} onChange={(event) => { setCompanyId(Number(event.target.value)); setProductIds([]); }}>
      {companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label><label>ФИО <input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label></div>
    <div className="form-row"><label>Телефон <input value={phone} onChange={(event) => setPhone(event.target.value)} /></label>
      <label>Почта <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label></div>
    <label>Предпочтительные способы связи <input value={channels} onChange={(event) => setChannels(event.target.value)} placeholder="Почта; Чат в ТГ" /></label>
    <fieldset><legend>Продукты контакта</legend><div className="customer-options">
      {products.filter((item) => item.company_id === companyId).map((item) => <label key={item.id}>
        <input type="checkbox" checked={productIds.includes(item.id)} onChange={(event) => setProductIds((current) =>
          event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /> {item.name}
      </label>)}
    </div></fieldset>
    {!productIds.length ? <p className="form-note">Выберите хотя бы один продукт этой компании.</p> : null}
    {error ? <ErrorAlert error={error} /> : null}
    <div className="modal-actions"><button className="primary" type="submit" disabled={!productIds.length}>Сохранить</button></div>
  </form>;
}
