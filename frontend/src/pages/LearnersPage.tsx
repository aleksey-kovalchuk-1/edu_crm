import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { useLearner, useLearners, useSaveLearner, type LearnerFull } from "../api/customerData";
import { useSession } from "../app/AuthGate";
import { Modal } from "../components/Modal";
import { ErrorAlert, queryFallback } from "../components/QueryState";
import { canEditCatalog } from "../lib/user";
import { useDebouncedValue } from "../lib/useDebouncedValue";

type Field = { name: keyof LearnerFull; label: string; type?: "date" | "email" };
const SECTIONS: { title: string; fields: Field[] }[] = [
  { title: "Личные данные", fields: [
    { name: "last_name", label: "Фамилия" }, { name: "first_name", label: "Имя" },
    { name: "middle_name", label: "Отчество" }, { name: "phone", label: "Телефон" },
    { name: "email", label: "Email", type: "email" }, { name: "snils", label: "СНИЛС" },
    { name: "gender", label: "Пол" }, { name: "birth_date", label: "Дата рождения", type: "date" },
  ] },
  { title: "Паспорт", fields: [
    { name: "passport_series", label: "Серия паспорта" },
    { name: "passport_number", label: "Номер паспорта" },
    { name: "passport_issued_by", label: "Кем выдан" },
    { name: "passport_issued_at", label: "Когда выдан", type: "date" },
    { name: "passport_department_code", label: "Код подразделения" },
  ] },
  { title: "Регистрация", fields: [
    { name: "registration_region", label: "Регион" },
    { name: "registration_locality", label: "Населённый пункт" },
    { name: "registration_street", label: "Улица" },
    { name: "registration_house", label: "Дом" },
    { name: "registration_apartment", label: "Квартира" },
    { name: "postal_code", label: "Индекс" },
  ] },
  { title: "Для документов", fields: [
    { name: "dative_last_name", label: "Фамилия в дательном падеже" },
    { name: "dative_first_name", label: "Имя в дательном падеже" },
    { name: "dative_middle_name", label: "Отчество в дательном падеже" },
  ] },
  { title: "Образование и диплом", fields: [
    { name: "education", label: "Образование" },
    { name: "diploma_profession", label: "Профессия по диплому" },
    { name: "diploma_institution", label: "Учебное заведение" },
    { name: "diploma_last_name", label: "Фамилия в дипломе" },
    { name: "diploma_series", label: "Серия диплома" },
    { name: "diploma_number", label: "Номер диплома" },
    { name: "diploma_registration_number", label: "Регистрационный номер диплома" },
    { name: "diploma_issued_at", label: "Дата выдачи диплома", type: "date" },
  ] },
];

export function LearnersPage() {
  const [params] = useSearchParams();
  const { user } = useSession();
  const canSeeFull = canEditCatalog(user.roles);
  const [search, setSearch] = useState("");
  const [detailId, setDetailId] = useState<number | undefined>(() => {
    const id = Number(params.get("id"));
    return Number.isSafeInteger(id) && id > 0 ? id : undefined;
  });
  const [creating, setCreating] = useState(false);
  const list = useLearners(useDebouncedValue(search));
  const detail = useLearner(canSeeFull ? detailId : undefined);

  return <div className="customer-workspace">
    <div className="customer-toolbar"><label>Поиск слушателя <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ФИО, телефон или email" /></label>
      {canSeeFull ? <button className="primary" onClick={() => setCreating(true)}>Добавить слушателя</button> : null}
    </div>
    <section className="panel">{queryFallback([list]) ?? <div className="table-wrap"><table className="data-table"><thead><tr>
      <th scope="col">Слушатель</th><th scope="col">Телефон</th><th scope="col">Email</th>{canSeeFull ? <th scope="col">Карточка</th> : null}
    </tr></thead><tbody>{list.data?.map((item) => <tr key={item.id}>
      <td><strong className="cell-title">{[item.last_name, item.first_name, item.middle_name].filter(Boolean).join(" ")}</strong></td>
      <td>{item.phone || "—"}</td><td>{item.email || "—"}</td>
      {canSeeFull ? <td><button className="text-button" onClick={() => setDetailId(item.id)}>Открыть анкету</button></td> : null}
    </tr>)}</tbody></table>{!list.data?.length ? <p className="empty">Слушатели не найдены.</p> : null}</div>}</section>
    {creating ? <Modal title="Новая анкета слушателя" close={() => setCreating(false)} wide>
      <LearnerEditor done={() => setCreating(false)} />
    </Modal> : null}
    {detailId !== undefined && canSeeFull ? <Modal title="Анкета слушателя" close={() => setDetailId(undefined)} wide>
      {queryFallback([detail]) ?? (detail.data ? <LearnerEditor record={detail.data} done={() => setDetailId(undefined)} /> : null)}
    </Modal> : null}
  </div>;
}

function LearnerEditor({ record, done }: { record?: LearnerFull; done: () => void }) {
  const save = useSaveLearner();
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(
    SECTIONS.flatMap((section) => section.fields.map((field) => [field.name, String(record?.[field.name] ?? "")])),
  ));
  async function submit(event: FormEvent) {
    event.preventDefault();
    const data: Record<string, string | null> = {};
    for (const section of SECTIONS) for (const field of section.fields) {
      const value = values[field.name]?.trim() ?? "";
      const old = record?.[field.name] ?? "";
      if (record ? value !== old : !!value || field.name === "last_name" || field.name === "first_name")
        data[field.name] = value || (record && field.name !== "last_name" && field.name !== "first_name" ? null : value);
    }
    await save.mutateAsync({ id: record?.id, data: data as Partial<LearnerFull> });
    done();
  }
  return <form className="customer-form" onSubmit={(event) => void submit(event)}>
    {SECTIONS.map((section) => <fieldset key={section.title}><legend>{section.title}</legend><div className="customer-field-grid">
      {section.fields.map((field) => <label key={field.name}>{field.label}
        <input type={field.type ?? "text"} required={field.name === "last_name" || field.name === "first_name"}
          value={values[field.name] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))} />
      </label>)}
    </div></fieldset>)}
    {save.error ? <ErrorAlert error={save.error} /> : null}
    <div className="modal-actions"><button className="primary" type="submit" disabled={save.isPending}>Сохранить анкету</button></div>
  </form>;
}
