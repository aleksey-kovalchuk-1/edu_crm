import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  LayoutDashboard,
  Building2,
  Columns3,
  ListChecks,
  ChartNoAxesCombined,
  GraduationCap,
  Search,
  Plus,
  ArrowUpRight,
  ArrowRight,
  ChevronRight,
  X,
  Users,
  BookOpen,
  Clock3,
  CircleCheck,
  CalendarDays,
  Download,
  RefreshCw,
  PanelLeftClose,
} from "lucide-react";
import {
  api,
  type University,
  type Launch,
  type Task,
  type Dashboard,
  type StageEvent,
} from "./api";

const pages = [
  { name: "Обзор", icon: LayoutDashboard },
  { name: "Учебные заведения", icon: Building2 },
  { name: "Взаимодействия", icon: Columns3 },
  { name: "Задачи", icon: ListChecks },
  { name: "Аналитика", icon: ChartNoAxesCombined },
];
const groups = [
  "Первый контакт",
  "Документы",
  "Внедрение",
  "Обучение",
  "Сопровождение",
];
const group = (stage: number) =>
  stage < 3 ? 0 : stage < 6 ? 1 : stage < 8 ? 2 : stage < 11 ? 3 : 4;
const format = (n: number) => new Intl.NumberFormat("ru-RU").format(n);
const date = (s: string) =>
  new Date(s + "T12:00:00").toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });
const initials = (s: string) =>
  s
    .split(" ")
    .slice(0, 2)
    .map((x) => x[0])
    .join("");

function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={close}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
      aria-label={title}
    >
      <div className="modal">
        <div className="section-head">
          <h2>{title}</h2>
          <button className="icon-button" onClick={close} aria-label="Закрыть">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

export default function App() {
  const [page, setPage] = useState("Обзор");
  const [search, setSearch] = useState("");
  const [universities, setUniversities] = useState<University[]>([]);
  const [launches, setLaunches] = useState<Launch[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stages, setStages] = useState<string[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [modal, setModal] = useState<"university" | "launch" | null>(null);
  const [selected, setSelected] = useState<Launch | null>(null);
  const [history, setHistory] = useState<StageEvent[]>([]);
  const [stageDraft, setStageDraft] = useState(0);
  const [menu, setMenu] = useState(false);
  const [onlyOverdue, setOnlyOverdue] = useState(false);

  async function load() {
    setError("");
    try {
      const [u, l, t, s, d] = await Promise.all([
        api<University[]>("/universities"),
        api<Launch[]>("/launches"),
        api<Task[]>("/tasks"),
        api<string[]>("/stages"),
        api<Dashboard>("/dashboard"),
      ]);
      setUniversities(u);
      setLaunches(l);
      setTasks(t);
      setStages(s);
      setDashboard(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "API недоступен");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  function navigate(name: string) {
    setPage(name);
    setSearch("");
    setOnlyOverdue(false);
    setMenu(false);
  }
  function openLaunch(l: Launch) {
    setSelected(l);
    setStageDraft(l.stage);
    setHistory([]);
    api<StageEvent[]>(`/launches/${l.id}/history`)
      .then(setHistory)
      .catch((e) => setError(e.message));
  }
  async function mutate(path: string, method: string, data: unknown) {
    setSaving(true);
    setError("");
    try {
      await api(path, method, data);
      await load();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
      return false;
    } finally {
      setSaving(false);
    }
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const data = Object.fromEntries(f.entries());
    if (modal === "launch") {
      Object.assign(data, {
        university_id: Number(f.get("university_id")),
        students: Number(f.get("students")),
      });
    }
    if (
      await mutate(
        modal === "university" ? "/universities" : "/launches",
        "POST",
        data,
      )
    )
      setModal(null);
  }
  const filtered = launches.filter(
    (l) =>
      `${l.program} ${l.university} ${l.city} ${l.owner}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!onlyOverdue || l.overdue),
  );
  const filteredUniversities = universities.filter((u) =>
    `${u.name} ${u.city} ${u.contact}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const filteredTasks = tasks.filter((t) =>
    `${t.title} ${t.owner}`.toLowerCase().includes(search.toLowerCase()),
  );
  const annual = dashboard?.annual ?? [];
  function exportCsv() {
    const escape = (v: string | number) =>
      '"' +
      String(v)
        .replace(/^[=+@-]/, "'$&")
        .replaceAll('"', '""') +
      '"';
    const rows = [
      ["Год", "Заявки", "Обучающиеся", "Потоки"],
      ...annual.map((x) => [
        x.year,
        x.applications,
        x.students,
        x.streams,
      ]),
    ];
    const url = URL.createObjectURL(
      new Blob(
        ["\ufeff" + rows.map((r) => r.map(escape).join(";")).join("\n")],
        { type: "text/csv;charset=utf-8" },
      ),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "edu-crm-analytics.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  const metrics = [
    {
      label: "Учебных заведений",
      value: dashboard?.universities ?? 0,
      icon: Building2,
      caption: "В едином реестре",
      color: "purple",
    },
    {
      label: "Программ в работе",
      value: dashboard?.launches ?? 0,
      icon: BookOpen,
      caption: "На всех этапах взаимодействия",
      color: "blue",
    },
    {
      label: "Обучающихся",
      value: dashboard?.students ?? 0,
      icon: Users,
      caption: "По текущим запускам",
      color: "green",
    },
    {
      label: "Требуют внимания",
      value: dashboard?.overdue ?? 0,
      icon: Clock3,
      caption: "Срок подготовки истёк",
      color: "orange",
    },
  ];

  const launchTable = (rows: Launch[]) => (
    <div className="table-wrap">
      <table>
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
              <td>
                <button className="table-link" onClick={() => openLaunch(l)}>
                  {l.program}
                </button>
                <small>{l.university}</small>
              </td>
              <td>
                <span className={`badge badge-${group(l.stage)}`}>
                  {stages[l.stage]}
                </span>
              </td>
              <td>
                <span className="owner">
                  <span className="avatar tiny">{initials(l.owner)}</span>
                  {l.owner}
                </span>
              </td>
              <td>{l.students}</td>
              <td className={l.overdue ? "danger" : ""}>{date(l.deadline)}</td>
              <td>
                <button
                  className="icon-button"
                  onClick={() => openLaunch(l)}
                  aria-label={`Открыть ${l.program}`}
                >
                  <ChevronRight size={18} />
                </button>
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
  const chartMax = Math.max(
    1,
    ...annual.flatMap((a) => [a.applications, a.students]),
  );
  const chart = (
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
                style={{
                  height: `${(a.applications / chartMax) * 145}px`,
                }}
                title={`Заявки: ${a.applications}`}
              >
                <span>{a.applications}</span>
              </div>
              <div
                className="bar lilac"
                style={{
                  height: `${(a.students / chartMax) * 145}px`,
                }}
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
  const taskList = (rows: Task[]) => (
    <div className="task-list">
      {rows.map((t) => (
        <div className={`task ${t.done ? "done" : ""}`} key={t.id}>
          <input
            type="checkbox"
            checked={t.done}
            disabled={saving}
            aria-label={t.title}
            onChange={() =>
              void mutate(`/tasks/${t.id}`, "PATCH", { done: !t.done })
            }
          />
          <div>
            <strong>{t.title}</strong>
            <small>
              {launches.find((l) => l.id === t.launch_id)?.program} · {t.owner}
            </small>
          </div>
          <span className="task-date">{date(t.deadline)}</span>
        </div>
      ))}
      {!rows.length && <p className="empty">Задач пока нет.</p>}
    </div>
  );

  return (
    <div className="app-shell">
      <aside className={menu ? "sidebar mobile-open" : "sidebar"}>
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            navigate("Обзор");
          }}
        >
          <span className="brand-mark">
            <GraduationCap size={27} />
          </span>
          <span>
            образование<span className="brand-sub">CRM · ЦИФРОВЫЕ НАВЫКИ</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">ИТ</span>
          <div>
            <strong>ИТ Школа</strong>
            <small>Рабочее пространство</small>
          </div>
          <ChevronRight size={16} />
        </div>
        <p className="nav-label">УПРАВЛЕНИЕ</p>
        <nav>
          {pages.map((p) => (
            <button
              key={p.name}
              className={page === p.name ? "nav-item active" : "nav-item"}
              onClick={() => navigate(p.name)}
            >
              <p.icon size={19} />
              {p.name}
              {p.name === "Задачи" && (
                <span className="nav-count">
                  {tasks.filter((t) => !t.done).length}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="status-dot" /> Демонстрационный контур
            <p>
              Единое пространство
              <br />
              для работы с образованием
            </p>
          </div>
          <div className="profile">
            <span className="avatar">ДМ</span>
            <div>
              <strong>Демо-менеджер</strong>
              <small>Предпросмотр системы</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button"
              aria-label="Меню"
              onClick={() => setMenu(!menu)}
            >
              <PanelLeftClose size={19} />
            </button>
            <span>Рабочее пространство</span>
            <ChevronRight size={15} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className="demo-label">ДЕМО</span>
            <span className="avatar tiny">ДМ</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <p className="eyebrow">ОБРАЗОВАТЕЛЬНЫЕ ПАРТНЁРСТВА</p>
              <h1>{page === "Обзор" ? "Всё важное — в одном месте" : page}</h1>
              <p className="subtitle">
                {page === "Обзор"
                  ? "Контролируйте взаимодействия и помогайте программам расти."
                  : page === "Взаимодействия"
                    ? "Полный цикл сотрудничества — от первого контакта до сопровождения."
                    : page === "Аналитика"
                      ? "Динамика спроса на обучение и результаты предыдущих лет."
                      : page === "Задачи"
                        ? "Ближайшие действия, сроки и ответственные."
                        : "Единая база партнёров, контактов и образовательных программ."}
              </p>
            </div>
            <button
              className="primary"
              disabled={loading || !dashboard}
              onClick={() =>
                setModal(page === "Учебные заведения" ? "university" : "launch")
              }
            >
              <Plus size={18} />
              {page === "Учебные заведения"
                ? "Добавить заведение"
                : "Новое взаимодействие"}
            </button>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => void load()}>
                <RefreshCw size={16} />
                Повторить
              </button>
            </div>
          )}
          {loading ? (
            <div className="loading">Загружаем рабочее пространство…</div>
          ) : !dashboard ? (
            <div className="empty">
              Не удалось подключиться к API. Запустите backend и повторите
              загрузку.
            </div>
          ) : (
            <>
              {page === "Обзор" && (
                <>
                  <section className="metrics">
                    {metrics.map((m) => (
                      <article className="metric" key={m.label}>
                        <div className="metric-top">
                          <span>{m.label}</span>
                          <m.icon size={19} className={`text-${m.color}`} />
                        </div>
                        <strong>{format(m.value)}</strong>
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
                          onClick={() => navigate("Взаимодействия")}
                        >
                          Открыть доску <ArrowUpRight size={16} />
                        </button>
                      </div>
                      <div className="pipeline">
                        {groups.map((g, i) => (
                          <button
                            className={`pipeline-stage stage-${i}`}
                            key={g}
                            onClick={() => navigate("Взаимодействия")}
                          >
                            <span className="pipeline-index">0{i + 1}</span>
                            <strong>
                              {
                                launches.filter((l) => group(l.stage) === i)
                                  .length
                              }
                            </strong>
                            <span>{g}</span>
                            <div className="pipeline-track">
                              <i
                                style={{
                                  width: `${Math.max(8, (launches.filter((l) => group(l.stage) === i).length / Math.max(1, launches.length)) * 100)}%`,
                                }}
                              />
                            </div>
                          </button>
                        ))}
                      </div>
                      <div className="pipeline-footer">
                        <CircleCheck size={16} /> Контроль сроков на каждом
                        этапе<span>{launches.length} взаимодействий</span>
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
                      {chart}
                    </section>
                  </div>
                  <section className="panel">
                    <div className="section-head">
                      <div>
                        <h2>
                          Программы в работе{" "}
                          <span className="count">{launches.length}</span>
                        </h2>
                        <p>Актуальные статусы образовательных партнёрств</p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("Взаимодействия")}
                      >
                        Все взаимодействия <ArrowRight size={16} />
                      </button>
                    </div>
                    {launchTable(launches.slice(0, 5))}
                  </section>
                  <section className="panel">
                    <div className="section-head">
                      <h2>Ближайшие задачи</h2>
                      <button
                        className="text-button"
                        onClick={() => navigate("Задачи")}
                      >
                        Все задачи <ArrowRight size={16} />
                      </button>
                    </div>
                    {taskList(tasks.filter((t) => !t.done).slice(0, 3))}
                  </section>
                </>
              )}
              {(page === "Учебные заведения" ||
                page === "Взаимодействия" ||
                page === "Задачи") && (
                <div className="toolbar">
                  <label className="search">
                    <Search size={18} />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Поиск по названию, городу или ответственному"
                      aria-label="Поиск"
                    />
                  </label>
                  {page === "Взаимодействия" && (
                    <button
                      className={onlyOverdue ? "filter selected" : "filter"}
                      onClick={() => setOnlyOverdue(!onlyOverdue)}
                    >
                      <Clock3 size={16} />
                      Требуют внимания
                    </button>
                  )}
                  <span className="muted">
                    {page === "Учебные заведения"
                      ? filteredUniversities.length
                      : page === "Задачи"
                        ? filteredTasks.length
                        : filtered.length}{" "}
                    записей
                  </span>
                </div>
              )}
              {page === "Учебные заведения" && (
                <div className="university-grid">
                  {filteredUniversities.map((u) => (
                    <article className="panel university-card" key={u.id}>
                      <div className="university-icon">
                        <Building2 size={25} />
                      </div>
                      <span className="muted">{u.city}</span>
                      <h2>{u.name}</h2>
                      <p>Контакт: {u.contact || "Не указан"}</p>
                      <div className="university-bottom">
                        <span>
                          {
                            launches.filter((l) => l.university_id === u.id)
                              .length
                          }{" "}
                          программ
                        </span>
                        <button
                          className="text-button"
                          onClick={() => {
                            setPage("Взаимодействия");
                            setSearch(u.name);
                          }}
                        >
                          Открыть <ArrowUpRight size={16} />
                        </button>
                      </div>
                    </article>
                  ))}
                  {!filteredUniversities.length && (
                    <p className="empty">Учебные заведения не найдены.</p>
                  )}
                </div>
              )}
              {page === "Взаимодействия" && (
                <div className="board">
                  {groups.map((g, i) => (
                    <section className="board-column" key={g}>
                      <div className="column-title">
                        <i className={`dot group-${i}`} />
                        <h2>{g}</h2>
                        <span>
                          {filtered.filter((l) => group(l.stage) === i).length}
                        </span>
                      </div>
                      {filtered
                        .filter((l) => group(l.stage) === i)
                        .map((l) => (
                          <button
                            className="launch-card"
                            key={l.id}
                            onClick={() => openLaunch(l)}
                          >
                            <span className="card-id">
                              ВЗ-{String(l.id).padStart(4, "0")}{" "}
                              <ArrowUpRight size={14} />
                            </span>
                            <h3>{l.program}</h3>
                            <p>{l.university}</p>
                            <span className={`badge badge-${i}`}>
                              {stages[l.stage]}
                            </span>
                            <div className="card-meta">
                              <span>
                                <Users size={14} />
                                {l.students}
                              </span>
                              <span className={l.overdue ? "danger" : ""}>
                                <CalendarDays size={14} />
                                {date(l.deadline)}
                              </span>
                            </div>
                            <div className="card-owner">
                              <span className="avatar tiny">
                                {initials(l.owner)}
                              </span>
                              {l.owner}
                            </div>
                          </button>
                        ))}
                      {!filtered.some((l) => group(l.stage) === i) && (
                        <div className="column-empty">Нет взаимодействий</div>
                      )}
                    </section>
                  ))}
                </div>
              )}
              {page === "Задачи" && (
                <section className="panel">{taskList(filteredTasks)}</section>
              )}
              {page === "Аналитика" && (
                <>
                  <div className="analytics-grid">
                    <section className="panel">
                      <div className="section-head">
                        <div>
                          <h2>Динамика образовательных программ</h2>
                          <p>Сопоставимые полные годы</p>
                        </div>
                        <button className="secondary" onClick={exportCsv}>
                          <Download size={16} />
                          CSV
                        </button>
                      </div>
                      {chart}
                    </section>
                    <section className="panel insight">
                      <span className="insight-icon">
                        <ChartNoAxesCombined size={26} />
                      </span>
                      <h2>Данные для решений</h2>
                      <p>
                        Сравнивайте заявки, число обучающихся и потоки за
                        предыдущие годы.
                      </p>
                      <div className="info-box">
                        Здесь показаны вымышленные данные. Импорт статистики
                        заказчика и прогнозирование будут подключены следующим
                        этапом.
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
                              <td>{format(a.applications)}</td>
                              <td>{format(a.students)}</td>
                              <td>{a.streams}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              )}
            </>
          )}
          <footer>
            Образование CRM <span>Рабочий шаблон · Данные вымышлены</span>
          </footer>
        </main>
      </div>
      {modal && (
        <Modal
          title={
            modal === "university"
              ? "Новое учебное заведение"
              : "Новое взаимодействие"
          }
          close={() => setModal(null)}
        >
          <form onSubmit={submit}>
            {modal === "university" ? (
              <>
                <label>
                  Название
                  <input
                    name="name"
                    required
                    maxLength={200}
                    placeholder="Название учебного заведения"
                  />
                </label>
                <label>
                  Город
                  <input
                    name="city"
                    required
                    maxLength={100}
                    placeholder="Город"
                  />
                </label>
                <label>
                  Контактное лицо
                  <input
                    name="contact"
                    maxLength={200}
                    placeholder="Имя координатора"
                  />
                </label>
              </>
            ) : (
              <>
                <label>
                  Учебное заведение
                  <select name="university_id" required defaultValue="">
                    <option value="" disabled>
                      Выберите из реестра
                    </option>
                    {universities.map((u) => (
                      <option value={u.id} key={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Программа
                  <input
                    name="program"
                    required
                    maxLength={200}
                    placeholder="Например, аналитика данных"
                  />
                </label>
                <label>
                  ИТ-продукт
                  <input
                    name="product"
                    required
                    maxLength={200}
                    placeholder="Например, PostgreSQL"
                  />
                </label>
                <label>
                  Ответственный
                  <input
                    name="owner"
                    required
                    maxLength={100}
                    placeholder="Имя менеджера"
                  />
                </label>
                <div className="form-row">
                  <label>
                    Обучающиеся
                    <input
                      name="students"
                      type="number"
                      min="0"
                      max="100000"
                      required
                      defaultValue="0"
                    />
                  </label>
                  <label>
                    Плановая дата запуска
                    <input name="deadline" type="date" required />
                  </label>
                </div>
              </>
            )}
            {error && (
              <p className="danger" role="alert">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary"
                onClick={() => setModal(null)}
              >
                Отмена
              </button>
              <button className="primary" disabled={saving}>
                {saving ? "Сохраняем…" : "Создать"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title={selected.program} close={() => setSelected(null)}>
          <p className="subtitle">{selected.university}</p>
          <div className="detail-grid">
            <div>
              <small>ИТ-продукт</small>
              <strong>{selected.product}</strong>
            </div>
            <div>
              <small>Ответственный</small>
              <strong>{selected.owner}</strong>
            </div>
            <div>
              <small>Обучающиеся</small>
              <strong>{selected.students}</strong>
            </div>
            <div>
              <small>Плановый запуск</small>
              <strong>{date(selected.deadline)}</strong>
            </div>
          </div>
          <label>
            Текущий этап
            <select
              value={stageDraft}
              onChange={(e) => setStageDraft(Number(e.target.value))}
            >
              {stages.map((s, i) => (
                <option key={s} value={i}>
                  {i + 1}. {s}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">
            В шаблоне можно выбрать любой этап, включая возврат на доработку.
            Изменение сохраняется в истории.
          </p>
          <div className="modal-actions">
            <button
              className="primary"
              disabled={saving || stageDraft === selected.stage}
              onClick={async () => {
                if (
                  await mutate(`/launches/${selected.id}`, "PATCH", {
                    stage: stageDraft,
                  })
                )
                  setSelected(null);
              }}
            >
              Сохранить этап
            </button>
          </div>
          {error && (
            <p className="danger" role="alert">
              {error}
            </p>
          )}
          <h3>История этапов</h3>
          <div className="history">
            {history.map((h) => (
              <div key={h.id}>
                <i className="dot purple" />
                <span>
                  {stages[h.stage]}
                  <small>
                    {new Date(
                      h.created_at.endsWith("Z") || h.created_at.includes("+")
                        ? h.created_at
                        : h.created_at + "Z",
                    ).toLocaleString("ru-RU")}
                  </small>
                </span>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
