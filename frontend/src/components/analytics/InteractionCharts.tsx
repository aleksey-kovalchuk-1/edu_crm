import { useEffect, useRef, useState } from "react";
import type { AnalyticsSnapshot } from "../../api/analytics";

const MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];

function monthLabel(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return `${MONTHS[month - 1]} ${year}`;
}

export function StageFunnel({ stages }: { stages: AnalyticsSnapshot["stages"] }) {
  const maximum = Math.max(1, ...stages.map((stage) => stage.count));
  return (
    <div className="analytics-funnel" role="list" aria-label="Количество вузов, достигших каждого этапа">
      {stages.map((stage, index) => (
        <div className="analytics-funnel-row" role="listitem" key={stage.name}>
          <span className="analytics-funnel-name">{stage.name}</span>
          <div className="analytics-funnel-track">
            <span className={`analytics-funnel-fill analytics-stage-${index}`} style={{ width: `${(stage.count / maximum) * 100}%` }} />
          </div>
          <strong className="analytics-funnel-value">{stage.count}</strong>
        </div>
      ))}
    </div>
  );
}

export function MonthlyLine({ months }: { months: AnalyticsSnapshot["monthly"] }) {
  const container = useRef<HTMLDivElement>(null);
  const [availableWidth, setAvailableWidth] = useState(0);
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    const measure = () => setAvailableWidth(Math.max(0, node.clientWidth - 48));
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const width = Math.max(660, months.length * 86 + 100, availableWidth);
  const height = 284;
  const left = 72;
  const top = 28;
  const bottom = 214;
  const right = width - 28;
  const max = Math.max(1, ...months.map((month) => month.count));
  const x = (index: number) => left + (months.length === 1 ? (right - left) / 2 : index * (right - left) / (months.length - 1));
  const y = (count: number) => bottom - count * (bottom - top) / max;
  const path = months.map((month, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(month.count)}`).join(" ");
  const ticks = [...new Set([0, Math.ceil(max / 2), max])];

  return (
    <div className="analytics-chart-scroll" ref={container} tabIndex={0} role="region" aria-label="Месячный график, горизонтальная прокрутка">
      <svg className="analytics-line-chart" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={`Внедрённые программы по месяцам: ${months.map((month) => `${monthLabel(month.month)} — ${month.count}`).join(", ")}`}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="analytics-grid-line" x1={left} y1={y(tick)} x2={right} y2={y(tick)} />
            <text className="analytics-axis-tick" x={left - 12} y={y(tick) + 4} textAnchor="end">{tick}</text>
          </g>
        ))}
        <line className="analytics-axis" x1={left} y1={top} x2={left} y2={bottom} />
        <line className="analytics-axis" x1={left} y1={bottom} x2={right} y2={bottom} />
        <path className="analytics-line" d={path} />
        {months.map((month, index) => (
          <g key={month.month}>
            <circle className="analytics-line-point" cx={x(index)} cy={y(month.count)} r="5" />
            <text className="analytics-point-value" x={x(index)} y={y(month.count) - 12} textAnchor="middle">{month.count}</text>
            <text className="analytics-axis-tick" x={x(index)} y={bottom + 21} textAnchor="middle">{monthLabel(month.month)}</text>
          </g>
        ))}
        <text className="analytics-axis-title" x={(left + right) / 2} y={height - 9} textAnchor="middle">Месяцы</text>
        <text className="analytics-axis-title" transform={`translate(19 ${(top + bottom) / 2}) rotate(-90)`} textAnchor="middle">Внедрённые программы</text>
      </svg>
    </div>
  );
}

export function UniversityRanking({ ranking }: { ranking: AnalyticsSnapshot["ranking"] }) {
  const maximumPrograms = Math.max(1, ...ranking.map((row) => row.programs));
  const maximumStudents = Math.max(1, ...ranking.map((row) => row.students));
  return (
    <div className="analytics-chart-scroll" tabIndex={0} role="region" aria-label="Рейтинг вузов, горизонтальная прокрутка">
      <div className="analytics-ranking" style={{ minWidth: Math.max(280, ranking.length * 118) }}>
        <div className="analytics-ranking-plot" role="list" aria-label="Рейтинг вузов по внедрённым программам и студентам" style={{ gridTemplateColumns: `repeat(${ranking.length}, minmax(112px, 1fr))` }}>
          {ranking.map((row) => (
            <div className="analytics-ranking-group" role="listitem" aria-label={`${row.name}: внедрённые программы — ${row.programs}, студенты — ${row.students}${row.students === 0 ? " (возможно, данные не заполнены)" : ""}`} key={row.id}>
              <div className="analytics-ranking-bars">
                <div className="analytics-ranking-bar analytics-program-bar" style={{ height: `${row.programs ? Math.max(2, row.programs / maximumPrograms * 100) : 0}%` }}>
                  <strong>{row.programs}</strong>
                </div>
                <div className="analytics-ranking-bar analytics-students-bar" style={{ height: `${row.students ? Math.max(2, row.students / maximumStudents * 100) : 0}%` }}>
                  <strong>{row.students === 0 ? "0*" : row.students}</strong>
                </div>
              </div>
              <span className="analytics-ranking-name">{row.name}</span>
            </div>
          ))}
        </div>
        <div className="analytics-ranking-legend">
          <span><i className="analytics-program-swatch" />Внедрённые программы</span>
          <span><i className="analytics-students-swatch" />Студенты</span>
        </div>
        <p className="analytics-ranking-note">Высота столбцов рассчитана отдельно для каждой категории; точные значения указаны над ними.</p>
        {ranking.some((row) => row.students === 0) && <p className="analytics-ranking-note">* 0 может означать незаполненные данные о студентах.</p>}
      </div>
    </div>
  );
}
