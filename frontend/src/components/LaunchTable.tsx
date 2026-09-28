import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import type { Launch } from "../api/types";
import { launchPath } from "../app/navigation";
import { formatDate, initials, launchCode, stageGroup } from "../lib/format";

export function LaunchTable({
  rows,
  stages,
}: {
  rows: Launch[];
  stages: string[];
}) {
  return (
    <div className="table-wrap">
      <table className="stack-table">
        <thead>
          <tr>
            <th>Программа / учебное заведение</th>
            <th>Этап</th>
            <th>Ответственный</th>
            <th>Обучающиеся</th>
            <th>Срок запуска</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => (
            <tr key={l.id}>
              <td data-label="Программа / учебное заведение">
                <Link className="table-link" to={launchPath(l.id)}>
                  {l.program}
                </Link>
                <small>
                  {l.university} · <span className="launch-code">{launchCode(l.id)}</span>
                </small>
              </td>
              <td data-label="Этап">
                <span className={`badge badge-${stageGroup(l.stage)}`}>
                  {stages[l.stage]}
                </span>
              </td>
              <td data-label="Ответственный">
                <span className="owner">
                  <span className="avatar tiny">{initials(l.owner)}</span>
                  {l.owner}
                </span>
              </td>
              <td data-label="Обучающиеся">{l.students}</td>
              <td data-label="Срок запуска" className={l.overdue ? "danger" : ""}>
                {formatDate(l.deadline)}
                {/* Colour alone does not say it: the word does. */}
                {l.overdue && <span className="overdue-note">просрочено</span>}
              </td>
              <td className="row-open">
                <Link
                  className="icon-button"
                  to={launchPath(l.id)}
                  aria-label={`Открыть ${l.program}`}
                >
                  <ChevronRight size={18} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <p className="empty">Нет программ по выбранным условиям.</p>
      )}
    </div>
  );
}
