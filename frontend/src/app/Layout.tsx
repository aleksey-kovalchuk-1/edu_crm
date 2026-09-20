import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  ChevronRight,
  GraduationCap,
  LogOut,
  PanelLeftClose,
  Plus,
} from "lucide-react";
import { useTaskList } from "../api/tasks";
import { CreateModal } from "../components/forms/CreateModal";
import { ErrorAlert } from "../components/QueryState";
import { canEditCatalog, roleLabel, userInitials } from "../lib/user";
import { useSession, useSignOut } from "./AuthGate";
import {
  NOT_FOUND_TITLE,
  findPage,
  isPageRoot,
  paths,
  visiblePages,
  type CreateKind,
} from "./navigation";

const CREATE_LABELS: Record<CreateKind, string> = {
  university: "Добавить заведение",
  launch: "Новое взаимодействие",
  contract: "Новый договор",
};

export function Layout() {
  const location = useLocation();
  const { user } = useSession();
  const logout = useSignOut();
  const [menu, setMenu] = useState(false);
  const [create, setCreate] = useState<CreateKind | null>(null);
  // Bumped by a sidebar click so re-opening the current page resets its local state.
  const [navResets, setNavResets] = useState(0);
  // Total tasks in "Мои задачи" scope; not filtered to open-only yet (counters land with T-104's filters).
  const tasks = useTaskList({ scope: "mine", limit: 1 });
  const page = findPage(location.pathname);
  const openTasks = tasks.data?.total;
  const closeMenu = () => setMenu(false);
  const initials = userInitials(user);
  // The server enforces roles; the interface only hides actions that would be refused.
  const createKind =
    page && page.create && isPageRoot(page, location.pathname) ? page.create : null;
  const canCreate =
    createKind !== null &&
    (createKind !== "university" || canEditCatalog(user.roles));

  return (
    <>
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
            {visiblePages(user.roles).map((p) => (
              <NavLink
                key={p.path}
                to={p.path}
                end={p.path === paths.overview}
                className={({ isActive }) =>
                  isActive ? "nav-item active" : "nav-item"
                }
                onClick={() => {
                  closeMenu();
                  setNavResets((n) => n + 1);
                }}
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
              <Link
                to={paths.profile}
                className="profile-link"
                onClick={closeMenu}
              >
                <span className="avatar" aria-hidden="true">
                  {initials}
                </span>
                <div>
                  <strong>{user.full_name || user.email}</strong>
                  <small>{roleLabel(user.roles)}</small>
                </div>
              </Link>
              <button
                className="icon-button logout-button"
                onClick={() => logout.mutate()}
                disabled={logout.isPending || logout.isSuccess}
                aria-label="Выйти"
                title="Выйти"
              >
                <LogOut size={17} />
              </button>
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
              <span className="avatar tiny" aria-hidden="true">
                {initials}
              </span>
            </div>
          </header>
          <main>
            <div className="page-heading">
              <div>
                <p className="eyebrow">ОБРАЗОВАТЕЛЬНЫЕ ПАРТНЁРСТВА</p>
                <h1>{page?.heading ?? NOT_FOUND_TITLE}</h1>
                {page && <p className="subtitle">{page.subtitle}</p>}
              </div>
              {createKind && canCreate && (
                <button className="primary" onClick={() => setCreate(createKind)}>
                  <Plus size={18} />
                  {CREATE_LABELS[createKind]}
                </button>
              )}
            </div>
            {logout.error && <ErrorAlert error={logout.error} />}
            {/*
              A new key per page (or sidebar click) resets page-local state; query-string
              changes (URL filters) keep the page mounted so inputs keep focus.
            */}
            <Outlet key={`${location.pathname}#${navResets}`} />
            <footer>
              Образование CRM <span>Рабочий шаблон · Данные вымышлены</span>
            </footer>
          </main>
        </div>
      </div>
      {create && <CreateModal kind={create} close={() => setCreate(null)} />}
    </>
  );
}
