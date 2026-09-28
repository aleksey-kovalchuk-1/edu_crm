import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { ChevronRight, GraduationCap, LogOut, Menu, Plus } from "lucide-react";
import { useBrand } from "../api/organization";
import { NotificationBell } from "../components/NotificationBell";
import { useTaskCounters } from "../api/tasks";
import { CreateModal } from "../components/forms/CreateModal";
import { ErrorAlert } from "../components/QueryState";
import { roleLabel, userInitials } from "../lib/user";
import { useSession, useSignOut } from "./AuthGate";
import {
  NOT_FOUND_TITLE,
  findPage,
  isPageRoot,
  paths,
  settingsPages,
  navGroups,
  type CreateKind,
} from "./navigation";
import { SettingsMenu } from "./SettingsMenu";

const CREATE_LABELS: Record<CreateKind, string> = {
  university: "Добавить заведение",
  launch: "Новое взаимодействие",
  contract: "Новый договор",
};

export function Layout() {
  const brand = useBrand();
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === "true";
  const location = useLocation();
  const { user } = useSession();
  const logout = useSignOut();
  const [menu, setMenu] = useState(false);
  const [create, setCreate] = useState<CreateKind | null>(null);
  // Bumped by a sidebar click so re-opening the current page resets its local state.
  const [navResets, setNavResets] = useState(0);
  // Open tasks in «Мои задачи»; the badge turns red while any of them is overdue.
  const taskCounters = useTaskCounters("mine");
  const page = findPage(location.pathname);
  const inSettings = !!page && settingsPages.includes(page);
  const openTasks = taskCounters.data?.open;
  const overdueTasks = taskCounters.data?.overdue ?? 0;
  const closeMenu = () => setMenu(false);
  // Escape closes the phone menu.
  useEffect(() => {
    if (!menu) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [menu]);
  const navigate = () => {
    closeMenu();
    setNavResets((n) => n + 1);
  };
  const initials = userInitials(user);
  // The server enforces roles; the interface only hides actions that would be refused.
  const createKind =
    page && page.create && isPageRoot(page, location.pathname) ? page.create : null;
  const canCreate = createKind !== null;

  return (
    <>
      <div className="app-shell">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            aria-label="Меню"
            aria-expanded={menu}
            aria-controls="app-menu"
            onClick={() => setMenu(!menu)}
          >
            <Menu size={20} aria-hidden="true" />
          </button>
          <Link to={paths.overview} className="brand" onClick={closeMenu}>
            <span className="brand-mark" aria-hidden="true">
              <GraduationCap size={20} />
            </span>
            <span className="brand-text">
              <span>UniCRM</span>
              {brand.data?.name && <small className="brand-org">{brand.data.name}</small>}
            </span>
          </Link>
          {inSettings && (
            <div className="breadcrumbs">
              <span>Настройки</span>
              <ChevronRight size={15} aria-hidden="true" />
              <strong>{page?.name ?? NOT_FOUND_TITLE}</strong>
            </div>
          )}
          <div className="topbar-right">
            {isDemoMode && <span className="demo-badge">Демонстрационный контур</span>}
            <NotificationBell />
            <Link to={paths.settingsProfile} className="profile-link" onClick={closeMenu}>
              <span className="avatar" aria-hidden="true">{initials}</span>
              <span className="profile-text">
                <strong>{user.full_name || user.email}</strong>
                <small>{roleLabel(user.roles)}</small>
              </span>
            </Link>
            <button
              className="icon-button logout-button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending || logout.isSuccess}
              aria-label="Выйти"
              title="Выйти"
            >
              <LogOut size={20} aria-hidden="true" />
            </button>
          </div>
        </header>
        <aside id="app-menu" className={menu ? "sidebar mobile-open" : "sidebar"}>
          <nav aria-label="Разделы">
            {navGroups(user.roles).map((g) => (
              <div key={g.id} className="nav-group" role="group" aria-labelledby={`nav-group-${g.id}`}>
                <div className="nav-group-label" id={`nav-group-${g.id}`}>{g.label}</div>
                {g.pages.map((p) => (
                  <NavLink
                    key={p.path}
                    to={p.path}
                    end={p.path === paths.overview}
                    className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
                    onClick={navigate}
                  >
                    <p.icon size={20} aria-hidden="true" />
                    {p.name}
                    {p.path === paths.tasks && openTasks !== undefined && (
                      <span
                        className={overdueTasks > 0 ? "nav-count nav-count-alert" : "nav-count"}
                        title={overdueTasks > 0 ? `Открытых: ${openTasks}, просрочено: ${overdueTasks}` : `Открытых: ${openTasks}`}
                      >
                        {openTasks}
                      </span>
                    )}
                  </NavLink>
                ))}
                {g.hasSettings && (
                  <SettingsMenu
                    pages={settingsPages}
                    currentPath={location.pathname}
                    userRoles={user.roles}
                    onNavigate={navigate}
                  />
                )}
              </div>
            ))}
          </nav>
        </aside>
        {menu && <div className="menu-backdrop" aria-hidden="true" onClick={closeMenu} />}
        <div className="main-shell">
          <main>
            <div className="page-heading">
              <div>
                <h1>{page?.heading ?? NOT_FOUND_TITLE}</h1>
              </div>
              {createKind && canCreate && (
                <button className="primary" onClick={() => setCreate(createKind)}>
                  <Plus size={18} aria-hidden="true" />
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
              UniCRM {isDemoMode && <span>Рабочий шаблон · Данные вымышлены</span>}
            </footer>
          </main>
        </div>
      </div>
      {create && <CreateModal kind={create} close={() => setCreate(null)} />}
    </>
  );
}
