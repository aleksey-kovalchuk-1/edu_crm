import { useState } from "react";
import {
  useApplyCustomerImport, useLearners, usePreviewCustomerImport,
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
  const preview = usePreviewCustomerImport();
  const apply = useApplyCustomerImport();
  const learners = useLearners();
  const chosen = KINDS.find((item) => item.value === kind)!;
  const unresolved = report?.rows.some((row) => row.candidate_ids.length && !resolved[String(row.row_number)]);
  const actionable = report?.rows.some((row) => row.status === "ok" ||
    (row.candidate_ids.length > 0 && !!resolved[String(row.row_number)]));
  function clear() { setReport(null); setApplied(false); setResolved({}); preview.reset(); apply.reset(); }
  async function runPreview() {
    if (!file) return;
    const next = await preview.mutateAsync({ kind, file });
    setReport(next);
    setApplied(false);
  }
  async function runApply() {
    if (!file || !report) return;
    const next = await apply.mutateAsync({ kind, file, resolved });
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
        {!applied ? <button type="button" className="primary" disabled={!!unresolved || apply.isPending || !actionable}
          onClick={() => void runApply()}>Применить</button> : null}
      </div>
      <p>Строк: {report.summary.rows}. Подходят: {report.summary.valid}. Ошибок: {report.summary.invalid}. Пропущено: {report.summary.skipped}.</p>
      {kind === "applications" ? <p className="form-note">Название файла не подтверждает оплату. Заявки сохраняются со статусом «Не подтверждено данными».</p> : null}
      {apply.error ? <ErrorAlert error={apply.error} /> : null}
      <div className="table-wrap"><table className="data-table"><thead><tr>
        <th scope="col">Строка</th><th scope="col">Результат</th><th scope="col">Сообщение</th><th scope="col">Сопоставление</th>
      </tr></thead><tbody>{report.rows.map((row) => <tr key={row.row_number}>
        <td>{row.row_number}</td><td>{row.status === "ok" ? "Готово" : row.status === "skipped" ? "Пропущено" : "Ошибка"}</td>
        <td>{[...row.errors, ...row.warnings].join("; ") || "—"}</td>
        <td>{row.candidate_ids.length ? <label>Слушатель
          <select value={resolved[String(row.row_number)] ?? ""} onChange={(event) => setResolved((current) => ({ ...current, [row.row_number]: Number(event.target.value) }))}>
            <option value="">Выберите вручную</option>
            {row.candidate_ids.map((id) => {
              const learner = learners.data?.find((item) => item.id === id);
              return <option key={id} value={id}>{learner ? `${learner.last_name} ${learner.first_name} — ${learner.email || learner.phone}` : `ID ${id}`}</option>;
            })}
          </select></label> : "—"}</td>
      </tr>)}</tbody></table></div>
    </section> : null}
  </div>;
}
