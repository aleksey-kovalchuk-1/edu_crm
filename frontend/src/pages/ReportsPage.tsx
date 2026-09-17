import { useState, type ChangeEvent, type FormEvent } from "react";
import { useItDirections, useItProducts, useUniversities } from "../api/catalogs";
import {
  FORMAT_LABELS,
  STATUS_LABELS,
  reportDownloadUrl,
  useCreateReport,
  useReportColumns,
  useReportJobs,
  type ReportFormat,
} from "../api/reports";
import { defaultWorkflow, sortedStatuses, useWorkflows } from "../api/workflows";
import { ReportStatusChart } from "../components/ReportStatusChart";
import { ErrorAlert, RefreshError, queryFallback } from "../components/QueryState";

const FORMATS = Object.keys(FORMAT_LABELS) as ReportFormat[];

const STATUS_BADGE: Record<string, string> = {
  queued: "badge-4",
  running: "badge-4",
  succeeded: "badge-3",
  failed: "badge-warning",
};

const selectedIds = (event: ChangeEvent<HTMLSelectElement>) =>
  Array.from(event.target.selectedOptions, (option) => Number(option.value));

export function ReportsPage() {
  const universities = useUniversities();
  const directions = useItDirections();
  const products = useItProducts();
  const workflows = useWorkflows();
  const columns = useReportColumns();
  const jobs = useReportJobs();
  const create = useCreateReport();

  const queries = [universities, directions, products, workflows, columns, jobs];
  const fallback = queryFallback(queries);

  const [periodFrom, setPeriodFrom] = useState("");
  const [periodTo, setPeriodTo] = useState("");
  const [universityIds, setUniversityIds] = useState<number[]>([]);
  const [directionIds, setDirectionIds] = useState<number[]>([]);
  const [productIds, setProductIds] = useState<number[]>([]);
  const [statusIds, setStatusIds] = useState<number[]>([]);
  const [responsible, setResponsible] = useState("");
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [format, setFormat] = useState<ReportFormat>("xlsx");
  const [formError, setFormError] = useState<unknown>(null);

  if (fallback) return fallback;

  const workflow = defaultWorkflow(workflows.data!);
  const statuses = sortedStatuses(workflow);
  const allColumns = columns.data!;

  const toggleColumn = (key: string) =>
    setSelectedColumns((current) => {
      // Nothing checked means "all columns"; unchecking the last one is the same as unchecking all of them.
      const active = current.length ? current : allColumns.map((c) => c.key);
      return active.includes(key) ? active.filter((c) => c !== key) : [...active, key];
    });

  const columnChecked = (key: string) => selectedColumns.length === 0 || selectedColumns.includes(key);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      {
        period_from: periodFrom || undefined,
        period_to: periodTo || undefined,
        university_ids: universityIds,
        it_direction_ids: directionIds,
        it_product_ids: productIds,
        status_ids: statusIds,
        responsible: responsible
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        columns: selectedColumns,
        format,
      },
      { onSuccess: () => setFormError(null), onError: (e: Error) => setFormError(e) },
    );
  };

  const lastJsonReport = jobs.data!.find((job) => job.status === "succeeded" && job.format === "json");

  return (
    <>
      <RefreshError queries={queries} />
      <div className="reports-layout">
        <section className="panel">
          <div className="section-head">
            <h2>Параметры отчёта</h2>
          </div>
          <form className="editor-form" onSubmit={submit} noValidate>
            <div className="row-actions">
              <label>
                Период с
                <input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
              </label>
              <label>
                по
                <input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
              </label>
            </div>
            <label>
              Учебные заведения
              <select multiple value={universityIds.map(String)} onChange={(e) => setUniversityIds(selectedIds(e))}>
                {universities.data!.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              ИТ-направления
              <select multiple value={directionIds.map(String)} onChange={(e) => setDirectionIds(selectedIds(e))}>
                {directions.data!.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              ИТ-продукты
              <select multiple value={productIds.map(String)} onChange={(e) => setProductIds(selectedIds(e))}>
                {products.data!.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.vendor} — {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Статус процесса «{workflow.name}»
              <select multiple value={statusIds.map(String)} onChange={(e) => setStatusIds(selectedIds(e))}>
                {statuses.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <small className="field-hint">Только статусы базового процесса; другие процессы фильтром статуса не сузить.</small>
            </label>
            <label>
              Ответственные (через запятую)
              <input value={responsible} onChange={(e) => setResponsible(e.target.value)} placeholder="Иван Петров, Анна Демо" />
            </label>
            <fieldset>
              <legend>Колонки</legend>
              {allColumns.map((c) => (
                <label className="toggle" key={c.key}>
                  <input type="checkbox" checked={columnChecked(c.key)} onChange={() => toggleColumn(c.key)} />
                  {c.label}
                </label>
              ))}
            </fieldset>
            <fieldset>
              <legend>Формат</legend>
              {FORMATS.map((f) => (
                <label className="toggle" key={f}>
                  <input type="radio" name="report-format" checked={format === f} onChange={() => setFormat(f)} />
                  {FORMAT_LABELS[f]}
                </label>
              ))}
            </fieldset>
            {formError ? <ErrorAlert error={formError} /> : null}
            <div className="modal-actions">
              <button className="primary" disabled={create.isPending}>
                {create.isPending ? "Отправляем…" : "Сформировать отчёт"}
              </button>
            </div>
          </form>
        </section>

        <section className="panel">
          <div className="section-head">
            <h2>Мои отчёты</h2>
          </div>
          {!jobs.data!.length ? (
            <div className="empty">Отчётов пока нет.</div>
          ) : (
            <ul className="report-jobs">
              {jobs.data!.map((job) => (
                <li key={job.id} className="report-job-row">
                  <span className={`badge ${STATUS_BADGE[job.status]}`}>{STATUS_LABELS[job.status]}</span>
                  <span>
                    #{job.id} · {FORMAT_LABELS[job.format]}
                  </span>
                  <span className="muted">{new Date(job.created_at).toLocaleString("ru-RU")}</span>
                  {job.status === "succeeded" && (
                    <a className="text-button" href={reportDownloadUrl(job.id)}>
                      Скачать
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {lastJsonReport && <ReportStatusChart jobId={lastJsonReport.id} />}
      </div>
    </>
  );
}
