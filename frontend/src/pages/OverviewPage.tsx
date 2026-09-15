import { useNavigate } from "react-router";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Building2,
  ChartNoAxesCombined,
  CircleCheck,
  Clock3,
  Users,
} from "lucide-react";
import {
  useDashboard,
  useLaunches,
  useStages,
  useTasks,
} from "../api/queries";
import { paths } from "../app/navigation";
import { AnnualChart } from "../components/AnnualChart";
import { LaunchTable } from "../components/LaunchTable";
import { RefreshError, queryFallback } from "../components/QueryState";
import { TaskList } from "../components/TaskList";
import { formatNumber, stageGroup, stageGroups } from "../lib/format";

export function OverviewPage() {
  const navigate = useNavigate();
  const dashboard = useDashboard();
  const launches = useLaunches();
  const tasks = useTasks();
  const stages = useStages();
  const queries = [dashboard, launches, tasks, stages];
  const fallback = queryFallback(queries);
  const d = dashboard.data;
  const launchList = launches.data;
  const taskList = tasks.data;
  const stageNames = stages.data;
  if (fallback || !d || !launchList || !taskList || !stageNames)
    return fallback;

  const metrics = [
    {
      label: "Учебных заведений",
      value: d.universities,
      icon: Building2,
      caption: "В едином реестре",
      color: "purple",
    },
    {
      label: "Программ в работе",
      value: d.launches,
      icon: BookOpen,
      caption: "На всех этапах взаимодействия",
      color: "blue",
    },
    {
      label: "Обучающихся",
      value: d.students,
      icon: Users,
      caption: "По текущим запускам",
      color: "green",
    },
    {
      label: "Требуют внимания",
      value: d.overdue,
      icon: Clock3,
      caption: "Срок подготовки истёк",
      color: "orange",
    },
  ];
  const inGroup = (i: number) =>
    launchList.filter((l) => stageGroup(l.stage) === i).length;

  return (
    <>
      <RefreshError queries={queries} />
      <section className="metrics">
        {metrics.map((m) => (
          <article className="metric" key={m.label}>
            <div className="metric-top">
              <span>{m.label}</span>
              <m.icon size={19} className={`text-${m.color}`} />
            </div>
            <strong>{formatNumber(m.value)}</strong>
            <small>
              <span className={`dot ${m.color}`} />
              {m.caption}
            </small>
          </article>
        ))}
      </section>
      <div className="overview-grid">
        <section className="panel pipeline-panel">
          <div className="section-head">
            <div>
              <h2>Цикл взаимодействия</h2>
              <p>Распределение программ по этапам</p>
            </div>
            <button
              className="text-button"
              onClick={() => navigate(paths.interactions)}
            >
              Открыть доску <ArrowUpRight size={16} />
            </button>
          </div>
          <div className="pipeline">
            {stageGroups.map((g, i) => (
              <button
                className={`pipeline-stage stage-${i}`}
                key={g}
                onClick={() => navigate(paths.interactions)}
              >
                <span className="pipeline-index">0{i + 1}</span>
                <strong>{inGroup(i)}</strong>
                <span>{g}</span>
                <div className="pipeline-track">
                  <i
                    style={{
                      width: `${Math.max(8, (inGroup(i) / Math.max(1, launchList.length)) * 100)}%`,
                    }}
                  />
                </div>
              </button>
            ))}
          </div>
          <div className="pipeline-footer">
            <CircleCheck size={16} /> Контроль сроков на каждом этапе
            <span>{launchList.length} взаимодействий</span>
          </div>
        </section>
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Интерес к обучению</h2>
              <p>Заявки и обучающиеся</p>
            </div>
            <ChartNoAxesCombined size={20} className="muted" />
          </div>
          <AnnualChart annual={d.annual} />
        </section>
      </div>
      <section className="panel">
        <div className="section-head">
          <div>
            <h2>
              Программы в работе{" "}
              <span className="count">{launchList.length}</span>
            </h2>
            <p>Актуальные статусы образовательных партнёрств</p>
          </div>
          <button
            className="text-button"
            onClick={() => navigate(paths.interactions)}
          >
            Все взаимодействия <ArrowRight size={16} />
          </button>
        </div>
        <LaunchTable rows={launchList.slice(0, 5)} stages={stageNames} />
      </section>
      <section className="panel">
        <div className="section-head">
          <h2>Ближайшие задачи</h2>
          <button
            className="text-button"
            onClick={() => navigate(paths.tasks)}
          >
            Все задачи <ArrowRight size={16} />
          </button>
        </div>
        <TaskList
          rows={taskList.filter((t) => !t.done).slice(0, 3)}
          launches={launchList}
        />
      </section>
    </>
  );
}
