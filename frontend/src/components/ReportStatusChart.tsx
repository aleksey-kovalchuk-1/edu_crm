import { useEffect, useState } from "react";
import { reportDownloadUrl } from "../api/reports";

interface ReportRow {
  status: string;
}

/**
 * Interaction count per status, computed from the same JSON a downloaded report shows -- so its numbers
 * can never drift from what the report itself says (T-053: "chart values match report values").
 */
export function ReportStatusChart({ jobId }: { jobId: number }) {
  const [rows, setRows] = useState<ReportRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(reportDownloadUrl(jobId), { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((body: { rows: ReportRow[] }) => {
        if (!cancelled) setRows(body.rows);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (failed) return null;
  if (!rows) return null;

  const counts = new Map<string, number>();
  for (const row of rows) counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
  const entries = [...counts.entries()];
  if (!entries.length) return null;
  const max = Math.max(1, ...entries.map(([, count]) => count));

  return (
    <section className="panel">
      <div className="section-head">
        <h2>Взаимодействия по статусам</h2>
        <span className="muted">Отчёт #{jobId}</span>
      </div>
      <div className="chart">
        <div className="bars">
          {entries.map(([status, count], index) => (
            <div className="bar-group" key={status}>
              <div className="bar-pair">
                <div
                  className={`bar group-${index % 5}`}
                  style={{ height: `${(count / max) * 145}px` }}
                  title={`${status}: ${count}`}
                >
                  <span>{count}</span>
                </div>
              </div>
              <small>{status}</small>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
