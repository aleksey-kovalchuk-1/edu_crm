import { useState } from "react";
import { Download } from "lucide-react";
import { analyticsPdfUrl, useInteractionAnalytics } from "../api/analytics";
import { useUniversities } from "../api/catalogs";
import { useSession } from "../app/AuthGate";
import { MonthlyLine, StageFunnel, UniversityRanking } from "../components/analytics/InteractionCharts";
import { MultiSelect } from "../components/MultiSelect";
import { RefreshError } from "../components/QueryState";

function todayInZone(timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function displayDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
}

function EmptyChart() {
  return <p className="analytics-empty">Нет данных за выбранный период</p>;
}

export function AnalyticsPage() {
  const { user } = useSession();
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  const profileZone = user.timezone?.trim() || "";
  const timeZone = profileZone || browserZone;
  const [period, setPeriod] = useState(() => {
    const today = todayInZone(timeZone || "UTC");
    return { from: `${today.slice(0, 4)}-01-01`, to: today };
  });
  const [selectedUniversities, setSelectedUniversities] = useState<number[]>([]);
  const universities = useUniversities();
  const periodInvalid = Boolean(period.from && period.to && period.from > period.to);
  const periodMissing = !period.from || !period.to;
  const monthCount = periodMissing ? 0 : (Number(period.to.slice(0, 4)) - Number(period.from.slice(0, 4))) * 12
    + Number(period.to.slice(5, 7)) - Number(period.from.slice(5, 7)) + 1;
  const periodTooLong = monthCount > 120;
  const ready = !periodInvalid && !periodMissing && !periodTooLong && Boolean(timeZone);
  const params = {
    period_from: period.from,
    period_to: period.to,
    time_zone: timeZone,
    university_id: selectedUniversities,
  };
  const analytics = useInteractionAnalytics(params, ready);
  const data = ready ? analytics.data : undefined;

  return (
    <div className="analytics-page">
      <section className="panel analytics-filter-panel" aria-labelledby="analytics-filters-title">
        <div className="section-head">
          <div>
            <h2 id="analytics-filters-title">Параметры аналитики</h2>
            <p>Период и вузы применяются ко всем трём графикам и PDF.</p>
          </div>
          {ready ? (
            <a className="secondary analytics-pdf-link" href={analyticsPdfUrl(params)} download>
              <Download size={16} aria-hidden="true" />
              Скачать PDF
            </a>
          ) : (
            <button className="secondary analytics-pdf-link" type="button" disabled>Скачать PDF</button>
          )}
        </div>
        <div className="analytics-filters">
          <div className="analytics-period">
            <span className="multi-select-label">Период аналитики</span>
            <div className="analytics-date-inputs">
              <input type="date" aria-label="Период с" value={period.from} onChange={(event) => setPeriod((current) => ({ ...current, from: event.target.value }))} />
              <span aria-hidden="true">—</span>
              <input type="date" aria-label="Период по" value={period.to} onChange={(event) => setPeriod((current) => ({ ...current, to: event.target.value }))} />
            </div>
          </div>
          <MultiSelect
            label="Вузы"
            allLabel="Все вузы"
            options={(universities.data ?? []).map((university) => ({ value: university.id, label: university.short_name || university.name }))}
            value={selectedUniversities}
            onChange={setSelectedUniversities}
          />
        </div>
        <p className="analytics-selection">
          {period.from && period.to ? `${displayDate(period.from)} – ${displayDate(period.to)}` : "Укажите обе даты"}
          {" · "}{selectedUniversities.length ? `Выбрано вузов: ${selectedUniversities.length}` : "Все вузы"}
        </p>
        {periodInvalid && <p className="danger inline-error" role="alert">Конец периода раньше начала.</p>}
        {periodTooLong && <p className="danger inline-error" role="alert">Период не может превышать 10 лет.</p>}
        {periodMissing && <p className="danger inline-error" role="alert">Укажите начало и конец периода.</p>}
        {!timeZone && <p className="danger inline-error" role="alert">Не удалось определить часовой пояс. Укажите его в профиле.</p>}
        {profileZone ? <p className="muted analytics-time-zone">Часовой пояс профиля: {profileZone}.</p>
          : browserZone && <p className="muted analytics-time-zone">Часовой пояс браузера: {browserZone}. Укажите часовой пояс в профиле для точного расчёта.</p>}
        <RefreshError queries={[universities]} />
      </section>

      <RefreshError queries={[analytics]} />
      <section className="panel analytics-chart-panel" aria-labelledby="analytics-stages-title">
        <div className="section-head"><div>
          <h2 id="analytics-stages-title">Вузы по этапам</h2>
          <p>Вуз учитывается на достигнутом этапе и на всех предыдущих.</p>
        </div></div>
        {!ready || analytics.isPending || analytics.isError ? <p className="muted">{!ready ? "Проверьте период." : analytics.isError ? "Не удалось загрузить данные." : "Загружаем аналитику…"}</p>
          : data?.has_stage_data ? <StageFunnel stages={data.stages} /> : <EmptyChart />}
      </section>

      <section className="panel analytics-chart-panel" aria-labelledby="analytics-months-title">
        <div className="section-head"><div>
          <h2 id="analytics-months-title">Внедрённые программы по месяцам</h2>
          <p>Датой внедрения считается переход взаимодействия в «Обучение».</p>
        </div></div>
        {!ready || analytics.isPending || analytics.isError ? <p className="muted">{!ready ? "Проверьте период." : analytics.isError ? "Не удалось загрузить данные." : "Загружаем аналитику…"}</p>
          : data?.has_implementation_data ? <MonthlyLine months={data.monthly} /> : <EmptyChart />}
      </section>

      <section className="panel analytics-chart-panel" aria-labelledby="analytics-ranking-title">
        <div className="section-head"><div>
          <h2 id="analytics-ranking-title">Рейтинг вузов</h2>
          <p>Топ‑5 по числу внедрённых программ; при равенстве — по числу студентов.</p>
        </div></div>
        {!ready || analytics.isPending || analytics.isError ? <p className="muted">{!ready ? "Проверьте период." : analytics.isError ? "Не удалось загрузить данные." : "Загружаем аналитику…"}</p>
          : data?.ranking.length ? <UniversityRanking ranking={data.ranking} /> : <EmptyChart />}
      </section>
    </div>
  );
}
