import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  /** Optional icon shown before the label. */
  icon?: ReactNode;
}

/**
 * The WAI-ARIA tab strip on its own: arrow keys, Home and End move between tabs (automatic
 * activation); only the selected tab is in the tab order. `panelId` is the tabpanel the caller
 * renders wherever its layout needs it (see {@link Tabs} for the strip-plus-panel pair).
 */
export function TabList({
  label,
  tabs,
  selected,
  onSelect,
  className,
  panelId,
  idPrefix,
}: {
  label: string;
  tabs: TabItem[];
  selected: string;
  onSelect: (id: string) => void;
  className?: string;
  panelId: string;
  /** Tab element ids are `${idPrefix}-tab-${tab.id}`, for the panel's aria-labelledby. */
  idPrefix: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = tabs.length - 1;
    const next =
      e.key === "ArrowRight"
        ? index === last ? 0 : index + 1
        : e.key === "ArrowLeft"
          ? index === 0 ? last : index - 1
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? last
              : null;
    if (next === null) return;
    e.preventDefault();
    onSelect(tabs[next].id);
    refs.current[next]?.focus();
  }

  return (
    <div className={className ? `tabs ${className}` : "tabs"} role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${t.id}`}
          aria-selected={t.id === selected}
          aria-controls={panelId}
          tabIndex={t.id === selected ? 0 : -1}
          className={t.id === selected ? "tab selected" : "tab"}
          onClick={() => onSelect(t.id)}
          onKeyDown={(e) => onKeyDown(e, i)}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** A tab strip directly followed by its panel. */
export function Tabs({
  label,
  tabs,
  selected,
  onSelect,
  children,
  className,
}: {
  label: string;
  tabs: TabItem[];
  selected: string;
  onSelect: (id: string) => void;
  children: ReactNode;
  /** Extra class on the tablist itself (e.g. to enlarge it), on top of the base "tabs" class. */
  className?: string;
}) {
  const baseId = useId();
  return (
    <>
      <TabList
        label={label}
        tabs={tabs}
        selected={selected}
        onSelect={onSelect}
        className={className}
        panelId={`${baseId}-panel`}
        idPrefix={baseId}
      />
      <div role="tabpanel" id={`${baseId}-panel`} aria-labelledby={`${baseId}-tab-${selected}`}>
        {children}
      </div>
    </>
  );
}
