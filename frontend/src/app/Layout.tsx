import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  ChevronRight,
  GraduationCap,
  PanelLeftClose,
  Plus,
} from "lucide-react";
import { useTasks } from "../api/queries";
import { CreateModal, type CreateKind } from "../components/forms/CreateModal";
import { LaunchDetailProvider } from "./LaunchDetail";
import { NOT_FOUND_TITLE, findPage, pages, paths } from "./navigation";

export function Layout() {
  const location = useLocation();
  const [menu, setMenu] = useState(false);
  const [create, setCreate] = useState<CreateKind | null>(null);
  const tasks = useTasks();
  const page = findPage(location.pathname);
  const openTasks = tasks.data?.filter((t) => !t.done).length;
  const closeMenu = () => setMenu(false);

  return (
    <LaunchDetailProvider>
      <div className="app-shell">
        <aside className={menu ? "sidebar mobile-open" : "sidebar"}>
          <Link to={paths.overview} className="brand" onClick={closeMenu}>
            <span className="brand-mark">
              <GraduationCap size={27} />
            </span>
            <span>
              образование
              <span className="brand-sub">CRM · ЦИФРОВЫЕ НАВЫКИ</span>
            </span>
          </Link>
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
              <NavLink
                key={p.path}
                to={p.path}
                end
                className={({ isActive }) =>
                  isActive ? "nav-item active" : "nav-item"
                }
                onClick={closeMenu}
              >
                <p.icon size={19} />
                {p.name}
                {p.path === paths.tasks && openTasks !== undefined && (
                  <span className="nav-count">{openTasks}</span>
                )}
              </NavLink>
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
              <strong>{page?.name ?? NOT_FOUND_TITLE}</strong>
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
                <h1>{page?.heading ?? NOT_FOUND_TITLE}</h1>
                {page && <p className="subtitle">{page.subtitle}</p>}
              </div>
              {page && (
                <button
                  className="primary"
                  onClick={() => setCreate(page.create)}
                >
                  <Plus size={18} />
                  {page.create === "university"
                    ? "Добавить заведение"
                    : "Новое взаимодействие"}
                </button>
              )}
            </div>
            {/* A new key per navigation resets page-local state (search, filters). */}
            <Outlet key={location.key} />
            <footer>
              Образование CRM <span>Рабочий шаблон · Данные вымышлены</span>
            </footer>
          </main>
        </div>
      </div>
      {create && <CreateModal kind={create} close={() => setCreate(null)} />}
    </LaunchDetailProvider>
  );
}
