import { useId, useRef, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import type { University } from "../../api/types";

type Option = Pick<University, "id" | "name" | "short_name">;

/** An inline picker so its scrollable list cannot be clipped by the surrounding panel. */
export function UniversityFilter({ options, value, onChange }: {
  options: Option[];
  value: number[];
  onChange: (next: number[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const panelId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const selected = options.filter((option) => value.includes(option.id));
  const summary = selected.length === 0 ? "Все вузы"
    : selected.length <= 2 ? selected.map((option) => option.short_name || option.name).join(", ")
      : `Выбрано ${selected.length}`;
  const term = search.trim().toLocaleLowerCase("ru-RU");
  const visible = options.filter((option) =>
    `${option.name} ${option.short_name}`.toLocaleLowerCase("ru-RU").includes(term),
  );

  function toggle(id: number) {
    onChange(value.includes(id) ? value.filter((current) => current !== id) : [...value, id]);
  }

  return (
    <div className="analytics-university-picker" role="group" aria-label="Вузы"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          setOpen(false);
          trigger.current?.focus();
        }
      }}>
      <span className="multi-select-label">Вузы</span>
      <button ref={trigger} type="button" className="analytics-university-trigger"
        aria-label={`Вузы: ${summary}`} aria-expanded={open} aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}>
        <span className="analytics-university-summary">{summary}</span><ChevronDown size={17} aria-hidden="true" />
      </button>
      {open && (
        <div className="analytics-university-panel" id={panelId}>
          <label className="analytics-university-search">
            <Search size={16} aria-hidden="true" />
            <input type="search" aria-label="Найти вуз" placeholder="Найти вуз" value={search}
              onChange={(event) => setSearch(event.target.value)} />
          </label>
          <div className="analytics-university-list" aria-label="Список вузов">
            {visible.length === 0 && <p className="muted">Вузы не найдены</p>}
            {visible.map((option) => (
              <label className="analytics-university-option" key={option.id}>
                <input type="checkbox" aria-label={option.short_name || option.name}
                  checked={value.includes(option.id)} onChange={() => toggle(option.id)} />
                <span>
                  <strong>{option.short_name || option.name}</strong>
                  {option.short_name && option.short_name !== option.name && <small>{option.name}</small>}
                </span>
              </label>
            ))}
          </div>
          <div className="analytics-university-actions">
            <span className="muted">{selected.length ? `${selected.length} из ${options.length}` : `Все ${options.length}`}</span>
            {selected.length > 0 && <button type="button" className="text-button" onClick={() => onChange([])}>Все вузы</button>}
            <button type="button" className="text-button" onClick={() => setOpen(false)}>Готово</button>
          </div>
        </div>
      )}
    </div>
  );
}
