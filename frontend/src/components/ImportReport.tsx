import { useState } from "react";
import type {
  ImportReport,
  ImportRowResult,
  ImportRowStatus,
  ImportStatus,
  ImportSummary,
} from "../api/imports";
import { formatNumber } from "../lib/format";

export const IMPORT_STATUS_LABELS: Record<ImportStatus, string> = {
  uploaded: "загружен",
  applied: "применён",
};

export function ImportStatusBadge({ status }: { status: ImportStatus }) {
  return (
    <span className={status === "applied" ? "badge badge-3" : "badge badge-1"}>
      {IMPORT_STATUS_LABELS[status] ?? status}
    </span>
  );
}

const ROW_STATUS: Record<ImportRowStatus, { label: string; className: string }> = {
  ok: { label: "без замечаний", className: "badge badge-3" },
  warning: { label: "с предупреждением", className: "badge badge-warning" },
  error: { label: "ошибка", className: "badge badge-danger" },
  skipped: { label: "пропущена", className: "badge badge-4" },
};

export const ACTION_LABELS = { create: "создание", update: "обновление" } as const;

const ENTITY_LABELS: Record<string, string> = {
  contracts: "Договоры",
  universities: "Учебные заведения",
  it_products: "ИТ-продукты",
  it_directions: "ИТ-направления",
  university_contacts: "Ответственные от вуза",
};

const entityLabel = (key: string) => ENTITY_LABELS[key] ?? key;

/** Non-zero entity counts in a stable order (known entities first). */
function counts(values: Record<string, number> | undefined) {
  const entries = Object.entries(values ?? {}).filter(([, n]) => n > 0);
  const order = Object.keys(ENTITY_LABELS);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  return entries.sort(([a], [b]) => rank(a) - rank(b));
}

/**
 * Summary cards and what is (or will be) created and updated.
 * `applied` switches the wording from the forecast to the result.
 */
export function ImportSummaryView({
  summary,
  applied = false,
}: {
  summary: ImportSummary;
  applied?: boolean;
}) {
  const cards: [string, number, string][] = [
    ["Строк в файле", summary.rows, ""],
    [applied ? "Записано" : "Корректных", summary.valid, "text-green"],
    ["С ошибками", summary.invalid, "danger"],
    ["Пропущено", summary.skipped, ""],
    ["С предупреждениями", summary.with_warnings, "warning-text"],
  ];
  const created = counts(summary.created);
  const updated = counts(summary.updated);
  return (
    <>
      <dl className="summary-cards">
        {cards.map(([label, value, tone]) => (
          <div className="summary-card" key={label}>
            <dt>{label}</dt>
            <dd className={tone || undefined}>{formatNumber(value)}</dd>
          </div>
        ))}
      </dl>
      <div className="import-effects">
        <EffectList title={applied ? "Создано" : "Будет создано"} items={created} />
        <EffectList title={applied ? "Обновлено" : "Будет обновлено"} items={updated} />
      </div>
    </>
  );
}

function EffectList({ title, items }: { title: string; items: [string, number][] }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map(([key, n]) => (
            <li key={key}>
              <span>{entityLabel(key)}</span>
              <strong>{formatNumber(n)}</strong>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted-text">Ничего</p>
      )}
    </div>
  );
}

type RowFilter = "all" | "error" | "warning" | "skipped";
const FILTERS: { id: RowFilter; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "error", label: "Ошибки" },
  { id: "warning", label: "Предупреждения" },
  { id: "skipped", label: "Пропущенные" },
];
const ROWS_STEP = 200;

const matchesFilter = (row: ImportRowResult, filter: RowFilter) =>
  filter === "all" || row.status === filter;

/** Row-by-row results with a status filter; long lists are shown in portions. */
export function ImportRowsTable({ report }: { report: ImportReport }) {
  const [filter, setFilter] = useState<RowFilter>("all");
  const [limit, setLimit] = useState(ROWS_STEP);
  const rows = report.rows.filter((r) => matchesFilter(r, filter));
  const shown = rows.slice(0, limit);

  return (
    <div className="import-rows">
      <div className="filter-group" role="group" aria-label="Показать строки">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={filter === f.id ? "filter selected" : "filter"}
            aria-pressed={filter === f.id}
            onClick={() => {
              setFilter(f.id);
              setLimit(ROWS_STEP);
            }}
          >
            {f.label}
            <span className="count">
              {report.rows.filter((r) => matchesFilter(r, f.id)).length}
            </span>
          </button>
        ))}
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <caption className="visually-hidden">Результаты по строкам файла</caption>
          <thead>
            <tr>
              <th scope="col">Строка</th>
              <th scope="col">Номер договора</th>
              <th scope="col">Результат</th>
              <th scope="col">Действие</th>
              <th scope="col">Сообщения</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.row_number}>
                <td>{r.row_number}</td>
                <td>{r.contract_number || <span className="muted">—</span>}</td>
                <td>
                  <span className={ROW_STATUS[r.status]?.className ?? "badge"}>
                    {ROW_STATUS[r.status]?.label ?? r.status}
                  </span>
                </td>
                <td>{r.action ? ACTION_LABELS[r.action] : <span className="muted">—</span>}</td>
                <td className="wrap">
                  {r.errors.length || r.warnings.length ? (
                    <ul className="row-messages">
                      {r.errors.map((m, i) => (
                        <li className="danger" key={`e${i}`}>
                          {m}
                        </li>
                      ))}
                      {r.warnings.map((m, i) => (
                        <li className="warning-text" key={`w${i}`}>
                          {m}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <p className="empty">Нет строк с таким результатом.</p>}
      </div>
      {rows.length > shown.length && (
        <div className="pagination">
          <span className="muted">
            Показано {shown.length} из {rows.length}
          </span>
          <button type="button" className="secondary" onClick={() => setLimit((n) => n + ROWS_STEP)}>
            Показать ещё
          </button>
        </div>
      )}
    </div>
  );
}
