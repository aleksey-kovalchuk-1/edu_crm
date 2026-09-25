import { Download } from "lucide-react";
import { API_BASE } from "../api/client";

/** PNG / PDF download links for a server-rendered chart (backend/app/chart_routes.py, D-222). */
export function ChartDownloads({ chart, title }: { chart: "annual" | "interactions-by-status"; title: string }) {
  return (
    <span className="chart-downloads">
      {(["png", "pdf"] as const).map((format) => (
        <a
          key={format}
          className="secondary"
          href={`${API_BASE}/charts/${chart}?format=${format}`}
          download
          aria-label={`Скачать «${title}» в ${format.toUpperCase()}`}
        >
          <Download size={14} aria-hidden="true" />
          {format.toUpperCase()}
        </a>
      ))}
    </span>
  );
}
