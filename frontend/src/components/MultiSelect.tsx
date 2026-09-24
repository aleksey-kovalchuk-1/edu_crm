import { ChevronDown } from "lucide-react";

export interface MultiSelectOption<T extends string | number> {
  value: T;
  label: string;
}

/**
 * A compact "any of these" picker: a native <details> disclosure (keyboard-operable with no extra
 * JS) whose summary reads «Все» or the chosen names, over a checkbox list. Nothing chosen = no filter.
 */
export function MultiSelect<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: MultiSelectOption<T>[];
  value: T[];
  onChange: (value: T[]) => void;
}) {
  const chosen = options.filter((o) => value.includes(o.value));
  const summary = !chosen.length
    ? "Все"
    : chosen.length <= 2
      ? chosen.map((o) => o.label).join(", ")
      : `Выбрано: ${chosen.length}`;

  return (
    <div className="multi-select">
      <span className="multi-select-label">{label}</span>
      <details>
        <summary aria-label={`${label}: ${summary}`}>
          <span className={chosen.length ? "multi-select-value" : "multi-select-value muted"}>{summary}</span>
          <ChevronDown size={15} aria-hidden="true" />
        </summary>
        <div className="multi-select-menu" role="group" aria-label={label}>
          {options.length === 0 && <p className="muted">Нет вариантов</p>}
          {options.map((o) => (
            <label key={String(o.value)} className="toggle">
              <input
                type="checkbox"
                checked={value.includes(o.value)}
                onChange={() =>
                  onChange(value.includes(o.value) ? value.filter((v) => v !== o.value) : [...value, o.value])
                }
              />
              {o.label}
            </label>
          ))}
          {chosen.length > 0 && (
            <button type="button" className="text-button" onClick={() => onChange([])}>
              Сбросить
            </button>
          )}
        </div>
      </details>
    </div>
  );
}
