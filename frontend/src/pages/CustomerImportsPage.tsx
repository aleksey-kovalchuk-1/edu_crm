import { useState } from "react";
import {
  useApplyCustomerImport, useCustomerImportHistory, useLearners, usePreviewCustomerImport,
  type ImportKind, type ImportReport,
} from "../api/customerData";
import { useSession } from "../app/AuthGate";
import { ErrorAlert } from "../components/QueryState";
import { canImportCatalogs } from "../lib/user";

const KINDS: { value: ImportKind; label: string; accept: string }[] = [
  { value: "vendors", label: "Компании и контакты", accept: ".xlsx,.xls" },
  { value: "learners", label: "Анкеты слушателей", accept: ".xlsx,.xls" },
  { value: "applications", label: "Заявки на курсы", accept: ".json" },
];
const MANUAL_FIELDS: Record<ImportKind, { value: string; label: string }[]> = {
  vendors: ["company", "products", "full_name", "phone", "email", "channels"].map((value) => ({ value, label: value })),
  learners: ["last_name", "first_name", "middle_name", "phone", "email", "snils", "passport_series", "passport_number",
    "passport_issued_by", "passport_issued_at", "passport_department_code", "gender", "birth_date", "registration_region",
    "registration_locality", "registration_street", "registration_house", "registration_apartment", "postal_code",
    "dative_first_name", "dative_last_name", "dative_middle_name", "education", "diploma_profession", "diploma_institution",
    "diploma_last_name", "diploma_number", "diploma_series", "diploma_registration_number", "diploma_issued_at"].map((value) => ({ value, label: value })),
  applications: [],
};
const CARD_PATH = { vendor_contact: "/vendors", learner: "/learners", course_application: "/applications" };
function columnWord(count: number) {
  if (count % 100 >= 11 && count % 100 <= 14) return "столбцов";
  return count % 10 === 1 ? "столбец" : count % 10 >= 2 && count % 10 <= 4 ? "столбца" : "столбцов";
}

export function CustomerImportsPage() {
  const { user } = useSession();
  if (!canImportCatalogs(user.roles)) return <section className="panel"><p className="empty">Импорт доступен руководителю и администратору.</p></section>;
  return <CustomerImportWorkspace />;
}

function CustomerImportWorkspace() {
  const [kind, setKind] = useState<ImportKind>("applications");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [applied, setApplied] = useState(false);
  const [resolved, setResolved] = useState<Record<string, number>>({});
  const [manual, setManual] = useState<Record<string, string>>({});
  const [mappingReviewed, setMappingReviewed] = useState(true);
  const preview = usePreviewCustomerImport();
  const apply = useApplyCustomerImport();
  const history = useCustomerImportHistory();
  const learners = useLearners();
  const chosen = KINDS.find((item) => item.value === kind)!;
  const unresolved = report?.rows.some((row) => row.candidate_ids.length && !resolved[String(row.row_number)]);
  const actionable = report?.rows.some((row) => row.status === "ok" ||
    (row.candidate_ids.length > 0 && !!resolved[String(row.row_number)]));
  function selectedMapping() {
    if (!report || !Object.values(manual).some(Boolean)) return undefined;
    const mapping = { ...report.mapping };
    for (const [header, field] of Object.entries(manual)) {
      if (!field) continue;
      delete mapping[field];
      for (const [oldField, oldHeader] of Object.entries(mapping)) if (oldHeader === header) delete mapping[oldField];
      mapping[field] = header;
    }
    return mapping;
  }
  function clear() { setReport(null); setApplied(false); setResolved({}); setManual({}); setMappingReviewed(true); preview.reset(); apply.reset(); }
  async function runPreview(mapping?: Record<string, string>) {
    if (!file) return;
    const next = await preview.mutateAsync({ kind, file, mapping });
    setReport(next);
    setApplied(false);
    setMappingReviewed(true);
  }
  async function runApply() {
    if (!file || !report) return;
    const next = await apply.mutateAsync({ kind, file, resolved, mapping: selectedMapping() });
    setReport(next);
    setApplied(true);
  }
  return <div className="customer-workspace">
    <section className="panel">
      <h2>Предварительная проверка</h2>
      <p className="muted">Выберите вид данных и файл. Проверка ничего не записывает в базу.</p>
      <div className="customer-toolbar">
        <label>Вид данных <select value={kind} onChange={(event) => { setKind(event.target.value as ImportKind); setFile(null); clear(); }}>
          {KINDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select></label>
        <label>Файл <input type="file" accept={chosen.accept} onChange={(event) => { setFile(event.target.files?.[0] ?? null); clear(); }} /></label>
        <button type="button" className="primary" disabled={!file || preview.isPending} onClick={() => void runPreview()}>Проверить файл</button>
      </div>
      {preview.error ? <ErrorAlert error={preview.error} /> : null}
    </section>
    {report ? <section className="panel">
      <div className="section-head"><h2>{applied ? "Результат загрузки" : "Результат проверки"}</h2>
        {!applied ? <button type="button" className="primary" disabled={!!unresolved || apply.isPending || !actionable || !mappingReviewed}
          onClick={() => void runApply()}>Применить</button> : null}
      </div>
      <p>Строк: {report.summary.rows}. Подходят: {report.summary.valid}. Ошибок: {report.summary.invalid}. Пропущено: {report.summary.skipped}.</p>
      {report.mapping ? <p>{Object.keys(report.mapping).length} {columnWord(Object.keys(report.mapping).length)} распознано. Шаблон: {report.template_version}.</p> : null}
      {report.mapping ? <details><summary>Сопоставление столбцов</summary><ul>{Object.entries(report.mapping).map(([field, header]) =>
        <li key={field}>{header} → {field}</li>)}</ul></details> : null}
      {report.unmapped_headers?.length ? <div className="form-note"><p>Не перенесены: {report.unmapped_headers.join(", ")}</p>
        {!applied && kind !== "applications" ? <>
          {report.unmapped_headers.map((header) => <label key={header}>{header} → <select value={manual[header] ?? ""}
            onChange={(event) => { setManual((current) => ({ ...current, [header]: event.target.value })); setMappingReviewed(false); }}>
            <option value="">Не переносить</option>{MANUAL_FIELDS[kind].map((field) => <option key={field.value} value={field.value}>{field.label}</option>)}
          </select></label>)}
          <button type="button" disabled={!Object.values(manual).some(Boolean) || preview.isPending}
            onClick={() => void runPreview(selectedMapping())}>Проверить сопоставление</button>
        </> : null}
      </div> : null}
      {kind === "applications" ? <p className="form-note">Название файла не подтверждает оплату. Заявки сохраняются со статусом «Не подтверждено данными».</p> : null}
      {apply.error ? <ErrorAlert error={apply.error} /> : null}
      <div className="table-wrap"><table className="data-table"><thead><tr>
        <th scope="col">Строка</th><th scope="col">Результат</th><th scope="col">Сообщение</th><th scope="col">Сопоставление</th>
      </tr></thead><tbody>{report.rows.map((row) => <tr key={row.row_number}>
        <td>{row.row_number}</td><td>{row.status === "ok" ? "Готово" : row.status === "skipped" ? "Пропущено" : "Ошибка"}</td>
        <td>{[...row.errors, ...row.warnings].join("; ") || "—"}</td>
        <td>{applied && report.record_links?.some((link) => link.row_number === row.row_number) ? (() => {
          const link = report.record_links!.find((item) => item.row_number === row.row_number)!;
          return <a href={`${CARD_PATH[link.entity_type]}?id=${link.entity_id}`}>Открыть карточку #{link.entity_id}</a>;
        })() : row.candidate_ids.length ? <label>Слушатель
          <select value={resolved[String(row.row_number)] ?? ""} onChange={(event) => setResolved((current) => ({ ...current, [row.row_number]: Number(event.target.value) }))}>
            <option value="">Выберите вручную</option>
            {row.candidate_ids.map((id) => {
              const learner = learners.data?.find((item) => item.id === id);
              return <option key={id} value={id}>{learner ? `${learner.last_name} ${learner.first_name} — ${learner.email || learner.phone}` : `ID ${id}`}</option>;
            })}
          </select></label> : "—"}</td>
      </tr>)}</tbody></table></div>
    </section> : null}
    <section className="panel"><h2>История загрузок</h2>
      {history.data?.length ? <ul>{history.data.map((batch) => <li key={batch.id}>
        Пакет {batch.id}: {KINDS.find((item) => item.value === batch.kind)?.label ?? batch.kind}, {batch.summary.rows} строк
      </li>)}</ul> : <p className="muted">Пока нет загрузок.</p>}
    </section>
  </div>;
}
