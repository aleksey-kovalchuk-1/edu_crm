import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router";
import { ChevronRight, Settings } from "lucide-react";
import type { PageMeta } from "./navigation";

// Small delay before a hover-triggered close, so a brief flick of the pointer off the
// menu area (e.g. while moving diagonally toward the panel) doesn't flash it shut.
const HOVER_CLOSE_DELAY_MS = 150;

export function SettingsMenu({
  pages,
  currentPath,
  userRoles,
  onNavigate,
}: {
  pages: PageMeta[];
  currentPath: string;
  userRoles: string[];
  /** Called (alongside the menu's own close) when an item is clicked — lets the parent
   *  close a mobile slide-over sidebar and reset page-local state, matching what the
   *  flat sidebar NavLinks already do on click. */
  onNavigate?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  // Set right before opening via ArrowDown, so the focus-first effect below knows to act.
  const focusFirstOnOpen = useRef(false);

  // Same rule visiblePages() uses in navigation.ts: no roles listed means everyone sees it,
  // otherwise the user needs at least one of the listed roles.
  const visible = pages.filter(
    (p) => !p.roles || p.roles.some((r) => userRoles.includes(r)),
  );
  const isActive = visible.some(
    (p) => currentPath === p.path || currentPath.startsWith(`${p.path}/`),
  );

  const cancelScheduledClose = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);
  const scheduleClose = useCallback(() => {
    cancelScheduledClose();
    closeTimer.current = setTimeout(() => {
      // Don't let a stray hover-triggered close steal focus from a keyboard user who is
      // still inside the panel (e.g. opened via keyboard, then a mouseleave fires because
      // the pointer happens to be elsewhere) — that would drop focus back to <body>.
      if (rootRef.current?.contains(document.activeElement)) return;
      setOpen(false);
    }, HOVER_CLOSE_DELAY_MS);
  }, [cancelScheduledClose]);
  const closeNow = useCallback(() => {
    cancelScheduledClose();
    setOpen(false);
  }, [cancelScheduledClose]);

  // Focus the first item once the panel has actually rendered for an ArrowDown-triggered open.
  useEffect(() => {
    if (open && focusFirstOnOpen.current) {
      focusFirstOnOpen.current = false;
      itemRefs.current[0]?.focus();
    }
  }, [open]);

  // Click (or tap) outside the whole trigger+panel area closes the menu. This also covers
  // touch devices, which never fire hover events but do fire click/mousedown.
  useEffect(() => {
    if (!open) return;
    function onDocumentMouseDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) closeNow();
    }
    document.addEventListener("mousedown", onDocumentMouseDown);
    return () => document.removeEventListener("mousedown", onDocumentMouseDown);
  }, [open, closeNow]);

  useEffect(() => cancelScheduledClose, [cancelScheduledClose]);

  // Escape closes the menu regardless of where focus currently is — the trigger/item
  // keydown handlers below only fire when focus is inside the menu, which misses the
  // hover-opened case where focus never moved into it.
  useEffect(() => {
    if (!open) return;
    function onDocumentKeyDown(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        closeNow();
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onDocumentKeyDown);
    return () => document.removeEventListener("keydown", onDocumentKeyDown);
  }, [open, closeNow]);

  function onRootMouseEnter() {
    cancelScheduledClose();
    setOpen(true);
  }
  function onRootMouseLeave() {
    scheduleClose();
  }

  function onTriggerClick() {
    setOpen((o) => !o);
  }

  // Tabbing focus out of the whole trigger+panel area (e.g. past the last item) closes it too.
  function onRootFocusOut(e: React.FocusEvent<HTMLDivElement>) {
    if (!rootRef.current?.contains(e.relatedTarget as Node | null)) closeNow();
  }

  function onTriggerKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      cancelScheduledClose();
      setOpen(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      cancelScheduledClose();
      focusFirstOnOpen.current = true;
      setOpen(true);
    } else if (e.key === "Escape" && open) {
      closeNow();
      triggerRef.current?.focus();
    }
  }

  function onItemKeyDown(index: number, e: KeyboardEvent<HTMLAnchorElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      itemRefs.current[Math.min(index + 1, visible.length - 1)]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (index === 0) triggerRef.current?.focus();
      else itemRefs.current[index - 1]?.focus();
    } else if (e.key === "Escape") {
      closeNow();
      triggerRef.current?.focus();
    }
  }

  return (
    <div
      className="settings-menu-root"
      data-settings-menu-root
      ref={rootRef}
      onMouseEnter={onRootMouseEnter}
      onMouseLeave={onRootMouseLeave}
      onBlur={onRootFocusOut}
    >
      <button
        type="button"
        ref={triggerRef}
        className={isActive ? "nav-item active" : "nav-item"}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onTriggerClick}
        onKeyDown={onTriggerKeyDown}
      >
        <Settings size={19} />
        Настройки
        <ChevronRight size={14} className="settings-menu-chevron" />
      </button>
      {open && (
        <div
          id={panelId}
          className="settings-menu-panel"
          role="menu"
          aria-label="Настройки"
        >
          {/*
            settings-menu-panel-inner carries the visible background/border/shadow; the
            outer settings-menu-panel is a transparent, zero-gap hover bridge (its
            padding-left extends the hoverable box right up against the trigger, with no
            dead space a pointer moving diagonally toward the panel could slip through).
          */}
          <div className="settings-menu-panel-inner" role="none">
            {visible.map((p, i) => (
              <Link
                key={p.path}
                to={p.path}
                role="menuitem"
                className="settings-menu-item"
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                onClick={() => {
                  closeNow();
                  onNavigate?.();
                }}
                onKeyDown={(e) => onItemKeyDown(i, e)}
              >
                <p.icon size={16} />
                {p.name}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
