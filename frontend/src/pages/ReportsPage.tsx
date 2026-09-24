import { useState } from "react";
import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { useItDirections, useItProducts, useUniversities } from "../api/catalogs";
import { reportExportUrl, useReportOptions, useReportPreview, type ReportFormat, type ReportParams } from "../api/reports";
import { MultiSelect } from "../components/MultiSelect";
import { RefreshError, queryFallback } from "../components/QueryState";
import { ruPlural } from "../components/tasks/taskDisplay";

const EMPTY: Omit<ReportParams, "column"> = {
  university_id: [],
  it_direction_id: [],
  it_product_id: [],
  owner: [],
  status_id: [],
};

const FORMATS: { format: ReportFormat; label: string; icon: typeof FileText }[] = [
  { format: "xlsx", label: "Excel (.xlsx)", icon: FileSpreadsheet },
  { format: "xls", label: "Excel 97 (.xls)", icon: FileSpreadsheet },
  { format: "pdf", label: "PDF", icon: FileText },
];

/**
 * Report on interactions with universities (specification: "generate reports for the selected
 * period ... in xls, xlsx, pdf formats according to selected columns"; D-221). The preview and
 * the downloads use the same query string, so the file is exactly what's on screen.
 */
export function ReportsPage() {
  const options = useReportOptions();
  const universities = useUniversities();
  const directions = useItDirections();
  const products = useItProducts();
  const [filters, setFilters] = useState<Omit<ReportParams, "column">>(EMPTY);
  const [period, setPeriod] = useState({ from: "", to: "" });
  const [columns, setColumns] = useState<string[] | null>(null);

  const defaultColumns = options.data?.columns.filter((c) => c.default).map((c) => c.key) ?? [];
  const selectedColumns = columns ?? defaultColumns;
  const periodInvalid = !!period.from && !!period.to && period.from > period.to;
  const params: ReportParams = {
    ...filters,
    period_from: period.from || undefined,
    period_to: period.to || undefined,
    // Keep the catalog's column order whatever order they were ticked in.
    column: options.data?.columns.map((c) => c.key).filter((k) => selectedColumns.includes(k)) ?? [],
  };
  const ready = !!options.data && params.column.length > 0 && !periodInvalid;
  const preview = useReportPreview(params, ready);

  const fallback = queryFallback([options]);
  if (fallback || !options.data) return fallback;
  const workflows = new Set(options.data.statuses.map((s) => s.workflow));
  const set = <K extends keyof typeof filters>(key: K) => (value: (typeof filters)[K]) => setFilters((f) => ({ ...f, [key]: value }));
  const hasFilters = period.from || period.to || Object.values(filters).some((v) => v.length);

  return (
    <>
      <RefreshError queries={[preview]} />
      <section className="panel report-builder" aria-label="Параметры отчёта">
        <div className="report-filters">
          <div className="report-period">
            <span className="multi-select-label">Период</span>
            <div className="report-period-inputs">
              <input
                type="date"
                aria-label="Период с"
                value={period.from}
                max={period.to || undefined}
                onChange={(e) => setPeriod((p) => ({ ...p, from: e.target.value }))}
              />
              <span aria-hidden="true">—</span>
              <input
                type="date"
                aria-label="Период по"
                value={period.to}
                min={period.from || undefined}
                onChange={(e) => setPeriod((p) => ({ ...p, to: e.target.value }))}
              />
            </div>
          </div>
          <MultiSelect
            label="Учебные заведения"
            options={(universities.data ?? []).map((u) => ({ value: u.id, label: u.short_name || u.name }))}
            value={filters.university_id}
            onChange={set("university_id")}
          />
          <MultiSelect
            label="ИТ-направления"
            options={(directions.data ?? []).map((d) => ({ value: d.id, label: d.name }))}
            value={filters.it_direction_id}
            onChange={set("it_direction_id")}
          />
          <MultiSelect
            label="ИТ-продукты"
            options={(products.data ?? []).map((p) => ({ value: p.id, label: `${p.vendor} — ${p.name}` }))}
            value={filters.it_product_id}
            onChange={set("it_product_id")}
          />
          <MultiSelect
            label="Ответственные"
            options={options.data.owners.map((o) => ({ value: o, label: o }))}
            value={filters.owner}
            onChange={set("owner")}
          />
          <MultiSelect
            label="Статусы"
            options={options.data.statuses.map((s) => ({ value: s.id, label: workflows.size > 1 ? `${s.name} (${s.workflow})` : s.name }))}
            value={filters.status_id}
            onChange={set("status_id")}
          />
        </div>
        {periodInvalid && (
          <p className="danger inline-error" role="alert">
            Конец периода раньше начала.
          </p>
        )}
        <fieldset className="report-columns">
          <legend>Колонки отчёта</legend>
          <div className="filter-toggle-row">
            {options.data.columns.map((c) => (
              <label key={c.key} className="filter-pill">
                <input
                  type="checkbox"
                  checked={selectedColumns.includes(c.key)}
                  onChange={() =>
                    setColumns(selectedColumns.includes(c.key) ? selectedColumns.filter((k) => k !== c.key) : [...selectedColumns, c.key])
                  }
                />
                {c.label}
              </label>
            ))}
          </div>
        </fieldset>
        {hasFilters && (
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setFilters(EMPTY);
              setPeriod({ from: "", to: "" });
            }}
          >
            Сбросить условия
          </button>
        )}
      </section>

      <div className="report-actions">
        <span className="muted" aria-live="polite">
          {preview.data
            ? `${preview.data.total} ${ruPlural(preview.data.total, "взаимодействие", "взаимодействия", "взаимодействий")}`
            : params.column.length === 0
              ? "Выберите хотя бы одну колонку"
              : ""}
        </span>
        <div className="report-downloads">
          <Download size={16} aria-hidden="true" />
          <span>Скачать:</span>
          {FORMATS.map(({ format, label, icon: Icon }) =>
            ready ? (
              <a key={format} className="secondary" href={reportExportUrl(params, format)} download>
                <Icon size={15} aria-hidden="true" />
                {label}
              </a>
            ) : (
              <button key={format} type="button" className="secondary" disabled>
                <Icon size={15} aria-hidden="true" />
                {label}
              </button>
            ),
          )}
        </div>
      </div>

      {preview.data && ready && (
        <div className="panel table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {preview.data.columns.map((c) => (
                  <th scope="col" key={c.key}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.data.rows.map((row, i) => (
                <tr key={i}>
                  {preview.data.columns.map((c) => (
                    <td key={c.key}>{row[c.key] === "" ? <span className="muted">—</span> : row[c.key]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!preview.data.rows.length && <p className="empty">Нет взаимодействий по выбранным условиям.</p>}
          {preview.data.total > preview.data.rows.length && (
            <p className="table-total muted">
              Показаны первые {preview.data.rows.length} из {preview.data.total} — в файле будут все.
            </p>
          )}
        </div>
      )}
    </>
  );
}
