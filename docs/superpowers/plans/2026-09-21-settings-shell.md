# Настройки Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Настройки" sidebar entry directly below "Процессы" with a submenu (hover/click/keyboard/touch, no dead-zone gap, short open animation) listing the 7 required settings pages in order, each routed to a real page — 6 temporary placeholder pages that later slices will replace one at a time, and one permanent placeholder ("Персональные данные", per spec item 6).

**Architecture:** A new `SettingsMenu` component owns all open/close interaction logic (hover-intent with a shared pointer boundary around trigger+panel so there's no crossable gap, click-to-toggle, keyboard (Enter/Space/Arrow/Escape), and touch (tap-to-open, tap-outside-to-close)) and renders a `role="menu"` flyout of `role="menuitem"` links. `navigation.ts` gets a new `settingsPages` list (separate from the flat `pages` array `visiblePages()` already renders) so `Layout.tsx` can render the flat list exactly as today, then append one `SettingsMenu` right after it — which, since "Процессы" is the last non-hidden entry in `pages` for every role that can see it, satisfies "directly below Процессы" for every role without special-casing.

**Tech Stack:** React + TypeScript + React Router v7, existing `.sidebar`/`.nav-item` CSS conventions in `frontend/src/styles.css`.

**Spec:** No separate spec doc — scoped in conversation on 2026-09-21 (full 7-section "Настройки" request); this is slice 1 of 8. See the conversation for the full request and the confirmed architecture: single deterministic `superadmin` role (slice 2) gates "Пользователи и роли" and "Резервное копирование" only; a real Keycloak Admin API integration (slice 2); a real email abstraction mirroring `app/sms.py` (slice 3-adjacent); a minimal scheduler for license-expiry notifications (slice 8).

## Global Constraints

- The submenu must work by hover, click, keyboard, and touch — not hover-only. Every interaction path must be independently testable.
- No dead zone: moving the pointer from the trigger into the panel (including diagonally) must never close the menu.
- Opens with a short CSS transition on hover; no such requirement is stated for click/keyboard/touch open (an instant toggle there is fine).
- Do not touch `paths.profile` (`/profile`) or `ProfilePage.tsx` in this slice — the existing phone-verification page stays exactly as it is; slice 3 decides how it relates to the new `/settings/profile`.
- Do not build real content for any of the 6 non-"Персональные данные" settings pages in this slice — placeholders only, clearly temporary, replaced one at a time by slices 2-8.
- "Персональные данные"'s placeholder is NOT temporary scaffolding — it is spec item 6's actual deliverable (a clearly labelled placeholder, permanently, until a future task adds real content). Word it differently from the other 6 so it doesn't read as "coming soon."
- `ROLES.superadmin` ("crm-superadmin") is added to the frontend role list now (harmless, matches no real user until slice 2 wires up the Keycloak role and backend), so "Пользователи и роли" and "Резервное копирование" are gated by it from the start and slice 2 doesn't need to touch `navigation.ts` again.
- Do not push or merge; local commits only.

---

### Task 1: Navigation data — paths, roles, settings pages list

**Files:**
- Modify: `frontend/src/lib/user.ts` (add `ROLES.superadmin`)
- Modify: `frontend/src/app/navigation.ts` (add 7 settings paths, 7 hidden `PageMeta` entries, a new `settingsPages` export, a `paths.settings` base)
- Test: `frontend/src/app/navigation.test.ts` (new file — check first whether a `navigation.test.ts` already exists; if not, this is a new file)

**Interfaces:**
- Produces: `ROLES.superadmin = "crm-superadmin"`; `paths.settingsProfile`, `paths.settingsOrganization`, `paths.settingsNotifications`, `paths.settingsSecurity`, `paths.settingsUsers`, `paths.settingsPersonalData`, `paths.settingsBackups` (all under `/settings/...`); `settingsPages: PageMeta[]` in the exact required order (Личный профиль, Организация, Уведомления, Безопасность, Пользователи и роли, Персональные данные, Резервное копирование), each with `hidden: true` (so `visiblePages()` never renders them in the flat list) and the two admin-only ones (`Пользователи и роли`, `Резервное копирование`) carrying `roles: [ROLES.superadmin]`. Task 3 imports `settingsPages` to render the submenu; Task 2's component takes a `pages: PageMeta[]` prop so it has no direct import-time dependency on this exact list (keeps it independently testable).

- [ ] **Step 1: Write the failing test**

Check whether `frontend/src/app/navigation.ts` already has a test file (`grep -rl "from \"./navigation\"" frontend/src --include="*.test.ts"` and look for one testing `navigation.ts` directly rather than through a page). If none exists, create `frontend/src/app/navigation.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { ROLES } from "../lib/user";
import { paths, settingsPages } from "./navigation";

describe("settings navigation data", () => {
  it("lists the seven settings pages in the required order", () => {
    expect(settingsPages.map((p) => p.name)).toEqual([
      "Личный профиль",
      "Организация",
      "Уведомления",
      "Безопасность",
      "Пользователи и роли",
      "Персональные данные",
      "Резервное копирование",
    ]);
  });

  it("marks every settings page hidden from the flat sidebar list", () => {
    expect(settingsPages.every((p) => p.hidden)).toBe(true);
  });

  it("gates Пользователи и роли and Резервное копирование to superadmin only", () => {
    const users = settingsPages.find((p) => p.name === "Пользователи и роли")!;
    const backups = settingsPages.find((p) => p.name === "Резервное копирование")!;
    expect(users.roles).toEqual([ROLES.superadmin]);
    expect(backups.roles).toEqual([ROLES.superadmin]);
  });

  it("leaves the other five settings pages open to every role", () => {
    const open = settingsPages.filter((p) => !["Пользователи и роли", "Резервное копирование"].includes(p.name));
    expect(open.every((p) => p.roles === undefined)).toBe(true);
  });

  it("gives every settings page a distinct path under /settings", () => {
    const settingsPaths = settingsPages.map((p) => p.path);
    expect(new Set(settingsPaths).size).toBe(7);
    expect(settingsPaths.every((p) => p.startsWith("/settings/"))).toBe(true);
  });
});
```

- [ ] **Step 2: Run it, confirm it fails (module has no `settingsPages` export yet)**

```bash
cd frontend && npm run test -- --run navigation.test.ts
```

- [ ] **Step 3: Add the role constant**

In `frontend/src/lib/user.ts`, add to `ROLES`:
```typescript
export const ROLES = {
  user: "crm-user",
  supervisor: "crm-supervisor",
  admin: "crm-admin",
  superadmin: "crm-superadmin",
} as const;
```
Do not add a label for it to `ROLE_LABELS` in this task — that display concern belongs to whichever later slice actually shows a superadmin badge/label (not required by this slice).

- [ ] **Step 4: Add the paths and settings pages list**

In `frontend/src/app/navigation.ts`, extend `paths`:
```typescript
  settings: "/settings",
  settingsProfile: "/settings/profile",
  settingsOrganization: "/settings/organization",
  settingsNotifications: "/settings/notifications",
  settingsSecurity: "/settings/security",
  settingsUsers: "/settings/users",
  settingsPersonalData: "/settings/personal-data",
  settingsBackups: "/settings/backups",
```
Import `ROLES` from `../lib/user` (check it isn't already imported under a different alias). After the existing `pages` array, add:
```typescript
export const settingsPages: PageMeta[] = [
  {
    path: paths.settingsProfile,
    name: "Личный профиль",
    icon: UserRound,
    heading: "Личный профиль",
    subtitle: "Имя, контакты, язык интерфейса и часовой пояс.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsOrganization,
    name: "Организация",
    icon: Building2,
    heading: "Организация",
    subtitle: "Реквизиты и контактные данные организации.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsNotifications,
    name: "Уведомления",
    icon: Bell,
    heading: "Уведомления",
    subtitle: "Какие события присылают уведомления и когда.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsSecurity,
    name: "Безопасность",
    icon: ShieldCheck,
    heading: "Безопасность",
    subtitle: "Активные сеансы и политика паролей.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsUsers,
    name: "Пользователи и роли",
    icon: Users,
    heading: "Пользователи и роли",
    subtitle: "Учётные записи, роли и заявки на доступ.",
    create: null,
    hidden: true,
    roles: [ROLES.superadmin],
  },
  {
    path: paths.settingsPersonalData,
    name: "Персональные данные",
    icon: FileLock2,
    heading: "Персональные данные",
    subtitle: "Обработка персональных данных.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsBackups,
    name: "Резервное копирование",
    icon: DatabaseBackup,
    heading: "Резервное копирование",
    subtitle: "Статус резервных копий базы данных и вложений.",
    create: null,
    hidden: true,
    roles: [ROLES.superadmin],
  },
];
```
Add the new icon imports (`Bell`, `ShieldCheck`, `Users`, `FileLock2`, `DatabaseBackup`, plus reuse the already-imported `UserRound`/`Building2`) to the existing `lucide-react` import at the top of the file. Check each icon name actually exists in the installed `lucide-react` version (`grep '"lucide-react"' frontend/package.json` for the version, then check the package's exports if unsure) — substitute the closest equivalent icon if any of these names don't exist in the installed version, keeping the substitution visually sensible (e.g. a shield-style icon for Безопасность, a people icon for Пользователи и роли, a database/archive icon for Резервное копирование).

- [ ] **Step 5: Run the test, confirm it passes; run the full frontend suite**

```bash
cd frontend && npm run test -- --run navigation.test.ts
npm run test -- --run
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/user.ts frontend/src/app/navigation.ts frontend/src/app/navigation.test.ts
git commit -m "feat(settings): add settings navigation data and superadmin role constant"
```

---

### Task 2: `SettingsMenu` component — the hover/click/keyboard/touch submenu

**Files:**
- Create: `frontend/src/app/SettingsMenu.tsx`
- Test: `frontend/src/app/SettingsMenu.test.tsx`

**Interfaces:**
- Consumes: `PageMeta[]` (a `pages` prop — decoupled from `navigation.ts`'s `settingsPages` so this component is independently testable with a small fixture list), the current pathname (a `currentPath: string` prop, so the component doesn't need `useLocation` itself and stays easily testable), and `userRoles: string[]` (to filter which of the passed pages are actually shown, mirroring `visiblePages`'s own role filter — reuse that exact filter logic rather than reimplementing it; export a small `filterByRole(pages, roles)` helper from `navigation.ts` in this task if `visiblePages`'s current body can be trivially factored to share it, or just inline the same one-line filter here if factoring feels like more change than the task warrants — your call, but don't diverge in behavior).
- Produces: `<SettingsMenu pages={...} currentPath={...} userRoles={...} />`, a self-contained trigger+panel. Task 3 renders exactly one of these in `Layout.tsx`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/SettingsMenu.test.tsx` — use a small fixture (3 pages) rather than the real 7, since this component's own tests should not depend on `navigation.ts`'s exact list (Task 1 already tests that list separately):

```typescript
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { UserRound } from "lucide-react";
import { SettingsMenu } from "./SettingsMenu";
import type { PageMeta } from "./navigation";

const PAGES: PageMeta[] = [
  { path: "/settings/a", name: "Пункт А", icon: UserRound, heading: "А", subtitle: "", create: null, hidden: true },
  { path: "/settings/b", name: "Пункт Б", icon: UserRound, heading: "Б", subtitle: "", create: null, hidden: true },
  { path: "/settings/c", name: "Только для суперадмина", icon: UserRound, heading: "В", subtitle: "", create: null, hidden: true, roles: ["crm-superadmin"] },
];

function renderMenu(props: Partial<React.ComponentProps<typeof SettingsMenu>> = {}) {
  return render(
    <MemoryRouter>
      <SettingsMenu pages={PAGES} currentPath="/" userRoles={["crm-user"]} {...props} />
    </MemoryRouter>,
  );
}

describe("SettingsMenu", () => {
  it("does not render the submenu until opened", () => {
    renderMenu();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("opens on hover and closes when the pointer leaves the whole menu area", async () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    fireEvent.mouseEnter(trigger.closest("[data-settings-menu-root]")!);
    expect(await screen.findByRole("menu")).toBeTruthy();
    fireEvent.mouseLeave(trigger.closest("[data-settings-menu-root]")!);
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("moving the pointer from the trigger into the panel does not close it (no dead zone)", async () => {
    renderMenu();
    const root = screen.getByRole("button", { name: /Настройки/ }).closest("[data-settings-menu-root]")!;
    fireEvent.mouseEnter(root);
    const panel = await screen.findByRole("menu");
    // Leaving the trigger sub-area but staying within the shared root must not close the menu:
    fireEvent.mouseLeave(screen.getByRole("button", { name: /Настройки/ }));
    fireEvent.mouseEnter(panel);
    expect(screen.getByRole("menu")).toBeTruthy();
  });

  it("opens and closes on click, independent of hover", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.click(trigger);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when a click lands outside the whole menu area", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("is keyboard operable: Enter opens, Escape closes and returns focus to the trigger", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("ArrowDown from the trigger moves focus into the first menu item", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /Настройки/ });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const items = screen.getAllByRole("menuitem");
    expect(document.activeElement).toBe(items[0]);
  });

  it("filters items by role — a plain crm-user never sees the superadmin-only item", () => {
    renderMenu({ userRoles: ["crm-user"] });
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    expect(screen.queryByRole("menuitem", { name: /Только для суперадмина/ })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Пункт А" })).toBeTruthy();
  });

  it("shows the superadmin-only item for a superadmin", () => {
    renderMenu({ userRoles: ["crm-superadmin"] });
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    expect(screen.getByRole("menuitem", { name: /Только для суперадмина/ })).toBeTruthy();
  });

  it("shows the trigger as active when the current path matches any item", () => {
    renderMenu({ currentPath: "/settings/a" });
    expect(screen.getByRole("button", { name: /Настройки/ }).className).toContain("active");
  });

  it("lists items in the exact order given", () => {
    renderMenu({ userRoles: ["crm-superadmin"] });
    fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
    const items = screen.getAllByRole("menuitem").map((el) => el.textContent);
    expect(items).toEqual(["Пункт А", "Пункт Б", "Только для суперадмина"]);
  });
});
```

- [ ] **Step 2: Run it, confirm it fails (module doesn't exist yet)**

```bash
cd frontend && npm run test -- --run SettingsMenu.test.tsx
```

- [ ] **Step 3: Implement `SettingsMenu.tsx`**

```tsx
import { useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { ChevronRight, Settings } from "lucide-react";
import type { PageMeta } from "./navigation";

const CLOSE_DELAY_MS = 150;

export function SettingsMenu({
  pages,
  currentPath,
  userRoles,
}: {
  pages: PageMeta[];
  currentPath: string;
  userRoles: string[];
}) {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  const visible = pages.filter((p) => !p.roles || p.roles.some((r) => userRoles.includes(r)));
  const isActive = visible.some((p) => currentPath === p.path || currentPath.startsWith(`${p.path}/`));

  function cancelClose() {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }
  function scheduleClose() {
    cancelClose();
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }
  function closeNow() {
    cancelClose();
    setOpen(false);
  }

  function onRootMouseEnter() {
    cancelClose();
    setOpen(true);
  }
  function onRootMouseLeave() {
    scheduleClose();
  }

  function onTriggerClick() {
    setOpen((o) => !o);
  }

  function onTriggerKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      requestAnimationFrame(() => itemRefs.current[0]?.focus());
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

  // Click outside the whole menu area closes it (covers touch too, via the browser's
  // synthetic click-after-tap when there's no hover support).
  function onRootBlur(e: React.FocusEvent<HTMLDivElement>) {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) closeNow();
  }

  return (
    <div
      className="settings-menu-root"
      data-settings-menu-root
      onMouseEnter={onRootMouseEnter}
      onMouseLeave={onRootMouseLeave}
      onBlur={onRootBlur}
    >
      <button
        type="button"
        ref={triggerRef}
        className={isActive ? "nav-item active" : "nav-item"}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={onTriggerClick}
        onKeyDown={onTriggerKeyDown}
      >
        <Settings size={19} />
        Настройки
        <ChevronRight size={14} className="settings-menu-chevron" />
      </button>
      {open && (
        <div className="settings-menu-panel" role="menu" aria-label="Настройки">
          {visible.map((p, i) => (
            <Link
              key={p.path}
              to={p.path}
              role="menuitem"
              className="settings-menu-item"
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              onClick={closeNow}
              onKeyDown={(e) => onItemKeyDown(i, e)}
            >
              <p.icon size={16} />
              {p.name}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
```
This is a starting sketch, not gospel — if implementing against the real tests above reveals a cleaner way to structure the hover-intent/no-dead-zone logic (e.g. `onMouseEnter`/`onMouseLeave` on the root div is usually sufficient by itself for "no dead zone" *as long as* the panel is a DOM descendant of that same root and positioned with no gap — verify this holds once you add the CSS in Step 4, and adjust the structure if a real gap sneaks in), adjust it — the tests are the actual requirement, this code is a reasonable starting point.

- [ ] **Step 4: Add CSS — short open animation, zero-gap flyout positioning**

Add to `frontend/src/styles.css` (near the existing `.nav-item` rules):
```css
.settings-menu-root {
  position: relative;
}
.settings-menu-chevron {
  margin-left: auto;
}
.settings-menu-panel {
  position: absolute;
  top: 0;
  left: 100%;
  /* Zero gap: no margin between trigger and panel — padding-left on the panel itself
     extends its hoverable box without creating dead space the pointer can leave through. */
  padding-left: 10px;
  min-width: 220px;
  animation: settings-menu-in 120ms ease-out;
}
.settings-menu-panel::before {
  /* The padding above is transparent but still part of the panel's own box (and still
     inside .settings-menu-root via normal DOM nesting), so hovering it never fires
     the root's mouseleave — this is what actually closes the dead-zone gap. */
  content: "";
}
@keyframes settings-menu-in {
  from { opacity: 0; transform: translateX(-4px); }
  to { opacity: 1; transform: translateX(0); }
}
.settings-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 7px;
  background: #2b1c47;
  color: #d8cbed;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  text-decoration: none;
}
.settings-menu-item:hover,
.settings-menu-item:focus-visible {
  background: #3a2660;
  color: #fff;
}
```
Wrap the actual visible items in an inner container with a solid background/shadow (so the transparent `padding-left` bridge doesn't look like part of the visible panel) — adjust the sketch above so `.settings-menu-panel` is the invisible zero-gap hover bridge and a nested `.settings-menu-panel-inner` (or similar) carries the visible background/border/shadow/border-radius, matching this app's existing panel styling conventions (check `.modal`/`.panel`'s existing box-shadow/border-radius values in `styles.css` and reuse them for visual consistency, don't invent new ones).

- [ ] **Step 5: Run the tests, confirm they pass; run the full frontend suite**

```bash
cd frontend && npm run test -- --run SettingsMenu.test.tsx
npm run test -- --run
npm run build
npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/SettingsMenu.tsx frontend/src/app/SettingsMenu.test.tsx frontend/src/styles.css
git commit -m "feat(settings): add the SettingsMenu hover/click/keyboard/touch submenu component"
```

---

### Task 3: Wire into Layout, add the 7 routed pages (6 temporary placeholders + the real Персональные данные placeholder)

**Files:**
- Modify: `frontend/src/app/Layout.tsx`
- Modify: `frontend/src/app/App.tsx`
- Create: `frontend/src/pages/settings/SettingsPlaceholderPage.tsx` (shared "coming in a later slice" component, parameterised by heading/subtitle)
- Create: `frontend/src/pages/settings/SettingsProfilePage.tsx`, `SettingsOrganizationPage.tsx`, `SettingsNotificationsPage.tsx`, `SettingsSecurityPage.tsx`, `SettingsUsersPage.tsx`, `SettingsBackupsPage.tsx` (each a thin wrapper around `SettingsPlaceholderPage`)
- Create: `frontend/src/pages/settings/SettingsPersonalDataPage.tsx` (the real, permanent placeholder — its own text, not the shared "coming later" wrapper)
- Test: `frontend/src/app/layout.test.tsx` (check whether a `Layout`-level test file already exists under this or a similar name first — if App.test.tsx already covers general navigation, extend that instead of creating a new file; follow whichever the codebase already does for `Layout`)

**Interfaces:**
- Consumes: `SettingsMenu` (Task 2), `settingsPages`/`paths` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to whichever existing test file covers `Layout`/general app navigation (find it first — likely `frontend/src/app/App.test.tsx`, given that's where the earlier `App.test.tsx:92` diff landed for previous nav work):

```typescript
describe("Настройки menu", () => {
  it("renders directly after Процессы for a supervisor, and reaches each settings page", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-supervisor"]) });
    renderApp("/");
    const nav = await screen.findByRole("navigation");
    const items = within(nav).getAllByRole("button").concat(within(nav).getAllByRole("link"));
    // "Процессы" is a link; "Настройки" is the SettingsMenu's own button — assert relative order:
    const processesIndex = within(nav).getByRole("link", { name: /Процессы/ });
    const settingsButton = within(nav).getByRole("button", { name: /Настройки/ });
    expect(processesIndex.compareDocumentPosition(settingsButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(settingsButton);
    fireEvent.click(within(nav).getByRole("menuitem", { name: "Личный профиль" }));
    expect(await screen.findByRole("heading", { name: "Личный профиль" })).toBeTruthy();
  });

  it("hides Пользователи и роли and Резервное копирование from a plain crm-user", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/");
    const nav = await screen.findByRole("navigation");
    fireEvent.click(within(nav).getByRole("button", { name: /Настройки/ }));
    expect(within(nav).queryByRole("menuitem", { name: "Пользователи и роли" })).toBeNull();
    expect(within(nav).queryByRole("menuitem", { name: "Резервное копирование" })).toBeNull();
  });

  it("Персональные данные is a real, distinctly-worded placeholder", async () => {
    mockApi();
    renderApp(paths.settingsPersonalData);
    expect(await screen.findByRole("heading", { name: "Персональные данные" })).toBeTruthy();
    expect(screen.queryByText(/скоро|появится в одном из следующих/i)).toBeNull();
  });
});
```
Check the exact helper names (`sessionFixture`, `mockApi`, `renderApp`) and the `<nav>` element's accessible role/label against `frontend/src/test/utils.tsx` and the current `Layout.tsx` markup (does the existing `<nav>` have an accessible name already, or does `getByRole("navigation")` need no name filter — check first) before finalizing; adjust the sketch to match what's actually there rather than assuming.

- [ ] **Step 2: Run it, confirm it fails**

```bash
cd frontend && npm run test -- --run App.test.tsx   # or wherever Step 1 landed
```

- [ ] **Step 3: Create the placeholder pages**

`frontend/src/pages/settings/SettingsPlaceholderPage.tsx`:
```tsx
export function SettingsPlaceholderPage({ heading, subtitle }: { heading: string; subtitle: string }) {
  return (
    <section className="panel">
      <h2>{heading}</h2>
      <p className="muted">{subtitle}</p>
      <p className="muted">Появится в одном из следующих этапов работы над разделом «Настройки».</p>
    </section>
  );
}
```
The 6 thin wrappers (example for one, repeat for the other 5 with their own heading/subtitle matching `navigation.ts`'s `settingsPages` entries exactly):
```tsx
import { SettingsPlaceholderPage } from "./SettingsPlaceholderPage";

export function SettingsProfilePage() {
  return <SettingsPlaceholderPage heading="Личный профиль" subtitle="Имя, контакты, язык интерфейса и часовой пояс." />;
}
```
`SettingsPersonalDataPage.tsx` (the real, permanent one — do not use `SettingsPlaceholderPage`):
```tsx
export function SettingsPersonalDataPage() {
  return (
    <section className="panel">
      <h2>Персональные данные</h2>
      <p className="muted">
        Здесь будет представлена информация об обработке персональных данных в CRM.
      </p>
    </section>
  );
}
```

- [ ] **Step 4: Register routes**

In `frontend/src/app/App.tsx`, add 7 routes inside the existing `<Route element={<Layout />}>` block, before the `path="*"` catch-all:
```tsx
<Route path="settings/profile" element={<SettingsProfilePage />} />
<Route path="settings/organization" element={<SettingsOrganizationPage />} />
<Route path="settings/notifications" element={<SettingsNotificationsPage />} />
<Route path="settings/security" element={<SettingsSecurityPage />} />
<Route path="settings/users" element={<SettingsUsersPage />} />
<Route path="settings/personal-data" element={<SettingsPersonalDataPage />} />
<Route path="settings/backups" element={<SettingsBackupsPage />} />
```
Add the corresponding imports.

- [ ] **Step 5: Render `SettingsMenu` in `Layout.tsx`**

Find where `visiblePages(user.roles).map(...)` renders the flat `<NavLink>` list (inside `<nav>`). Immediately after that `.map(...)` call's closing, add:
```tsx
<SettingsMenu pages={settingsPages} currentPath={location.pathname} userRoles={user.roles} />
```
Import `SettingsMenu` from `./SettingsMenu` and `settingsPages` from `./navigation`.

- [ ] **Step 6: Run the tests, confirm they pass; run the full frontend suite**

```bash
cd frontend && npm run test -- --run
npm run build
npm run lint
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/Layout.tsx frontend/src/app/App.tsx frontend/src/pages/settings/ frontend/src/app/App.test.tsx
git commit -m "feat(settings): wire the Настройки menu into the sidebar with routed placeholder pages"
```

## Self-Review Notes

- **Spec coverage:** sidebar placement directly below Процессы (Task 3's render-order argument) ✓. Hover open with short animation (Task 2 CSS) ✓. Close on pointer-leave-whole-area (Task 2's root mouseenter/mouseleave + tests) ✓. No dead-zone gap (Task 2's zero-gap CSS + dedicated test) ✓. Click/keyboard/touch support (Task 2's click handler, keydown handlers, and touch's reliance on click/blur which already covers tap devices — no hover assumed) ✓. Exact 7-item order (Task 1's array order + Task 2's rendering in array order, both tested) ✓. Персональные данные as a real, distinct, permanent placeholder vs. the other 6 as temporary scaffolding (Task 3 Step 3, two different components, tested for wording difference) ✓.
- **Placeholder scan:** no TBD/"add later" left as an unfollowed instruction — every placeholder page's content is fully written out, not a stub comment.
- **Type/name consistency:** `SettingsMenu`'s prop names (`pages`, `currentPath`, `userRoles`) are the same in Task 2's definition and Task 3's usage. `settingsPages`/`paths.settings*` names are the same in Task 1's definition and Tasks 2-3's consumption.
