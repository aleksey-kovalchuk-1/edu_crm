import { ChartNoAxesCombined, Download } from "lucide-react";
import { useDashboard } from "../api/queries";
import type { AnnualMetric } from "../api/types";
import { AnnualChart } from "../components/AnnualChart";
import { RefreshError, queryFallback } from "../components/QueryState";
import { formatNumber, toCsv } from "../lib/format";

function exportCsv(annual: AnnualMetric[]) {
  const rows = [
    ["Год", "Заявки", "Обучающиеся", "Потоки"],
    ...annual.map((x) => [x.year, x.applications, x.students, x.streams]),
  ];
  const url = URL.createObjectURL(
    new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "edu-crm-analytics.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export function AnalyticsPage() {
  const dashboard = useDashboard();
  const queries = [dashboard];
  const fallback = queryFallback(queries);
  const annual = dashboard.data?.annual;
  if (fallback || !annual) return fallback;

  return (
    <>
      <RefreshError queries={queries} />
      <div className="analytics-grid">
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Динамика образовательных программ</h2>
              <p>Сопоставимые полные годы</p>
            </div>
            <button className="secondary" onClick={() => exportCsv(annual)}>
              <Download size={16} />
              CSV
            </button>
          </div>
          <AnnualChart annual={annual} />
        </section>
        <section className="panel insight">
          <span className="insight-icon">
            <ChartNoAxesCombined size={26} />
          </span>
          <h2>Данные для решений</h2>
          <p>
            Сравнивайте заявки, число обучающихся и потоки за предыдущие годы.
          </p>
          <div className="info-box">
            Здесь показаны вымышленные данные. Импорт статистики заказчика и
            прогнозирование будут подключены следующим этапом.
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="section-head">
          <h2>Показатели по годам</h2>
          <span className="demo-label">ДЕМО</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Год</th>
                <th>Заявки</th>
                <th>Обучающиеся</th>
                <th>Потоки за год</th>
              </tr>
            </thead>
            <tbody>
              {annual.map((a) => (
                <tr key={a.year}>
                  <td>{a.year}</td>
                  <td>{formatNumber(a.applications)}</td>
                  <td>{formatNumber(a.students)}</td>
                  <td>{a.streams}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
