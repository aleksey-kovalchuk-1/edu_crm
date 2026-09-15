import type { AnnualMetric } from "../api/types";

const BAR_HEIGHT = 145;

export function AnnualChart({ annual }: { annual: AnnualMetric[] }) {
  const max = Math.max(1, ...annual.flatMap((a) => [a.applications, a.students]));
  return (
    <div className="chart">
      <div className="chart-legend">
        <span>
          <i className="dot purple" />
          Заявки
        </span>
        <span>
          <i className="dot lilac" />
          Обучающиеся
        </span>
      </div>
      <div className="bars">
        {annual.map((a) => (
          <div className="bar-group" key={a.year}>
            <div className="bar-pair">
              <div
                className="bar purple"
                style={{ height: `${(a.applications / max) * BAR_HEIGHT}px` }}
                title={`Заявки: ${a.applications}`}
              >
                <span>{a.applications}</span>
              </div>
              <div
                className="bar lilac"
                style={{ height: `${(a.students / max) * BAR_HEIGHT}px` }}
                title={`Обучающиеся: ${a.students}`}
              >
                <span>{a.students}</span>
              </div>
            </div>
            <small>{a.year}</small>
          </div>
        ))}
      </div>
      <p className="muted chart-note">
        Полные календарные годы · демонстрационная статистика
      </p>
    </div>
  );
}
