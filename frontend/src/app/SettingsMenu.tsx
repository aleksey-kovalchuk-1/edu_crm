import { useId, useState } from "react";
import { NavLink } from "react-router";
import { ChevronDown, Settings } from "lucide-react";
import type { PageMeta } from "./navigation";

/**
 * «Настройки» as a group inside the side menu (spec §3.2): a disclosure button and a list of
 * links. It opens by click, tap or keyboard only — no hover — so a touch tap (which fires hover
 * and then click) opens it instead of opening and closing it at once. It is open on settings pages.
 */
export function SettingsMenu({
  pages,
  currentPath,
  userRoles,
  onNavigate,
}: {
  pages: PageMeta[];
  currentPath: string;
  userRoles: string[];
  /** Called when an item is chosen: lets the layout close the phone menu and reset page state. */
  onNavigate?: () => void;
}) {
  const listId = useId();
  // Same rule visiblePages() uses: no roles listed means everyone sees it.
  const visible = pages.filter((p) => !p.roles || p.roles.some((r) => userRoles.includes(r)));
  const inSettings = visible.some((p) => currentPath === p.path || currentPath.startsWith(`${p.path}/`));
  // null = the user has not toggled it yet, so it follows the current page.
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? inSettings;

  return (
    <div className="settings-group">
      <button
        type="button"
        className={inSettings ? "nav-item active" : "nav-item"}
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setToggled(!open)}
      >
        <Settings size={20} aria-hidden="true" />
        Настройки
        <ChevronDown size={16} className="settings-group-chevron" aria-hidden="true" />
      </button>
      <ul id={listId} className="settings-group-list" hidden={!open}>
        {visible.map((p) => (
          <li key={p.path}>
            <NavLink
              to={p.path}
              className={({ isActive }) => (isActive ? "nav-subitem active" : "nav-subitem")}
              onClick={onNavigate}
            >
              <p.icon size={18} aria-hidden="true" />
              {p.name}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}
