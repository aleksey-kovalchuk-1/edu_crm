import { Columns3 } from "lucide-react";

export const OPTIONAL_COLUMNS: { key: string; label: string }[] = [
  { key: "status", label: "Статус" },
  { key: "deadline", label: "Срок" },
  { key: "assignees", label: "Исполнители" },
  { key: "priority", label: "Приоритет" },
  { key: "creator", label: "Постановщик" },
  { key: "updated_at", label: "Изменена" },
  { key: "university", label: "Учебное заведение" },
  { key: "created_at", label: "Дата создания" },
];

/** Institution and interaction already show under each title, so they are not a default column. */
export const DEFAULT_COLUMNS = ["status", "deadline", "assignees", "priority", "creator", "updated_at"];

/** Native <details> disclosure — keyboard-operable with no extra JS (spec: "configurable ... columns"). */
export function TaskColumnPicker({ columns, onChange }: { columns: string[]; onChange: (columns: string[]) => void }) {
  return (
    <details className="column-picker">
      <summary>
        <Columns3 size={15} aria-hidden="true" />
        Колонки
      </summary>
      <div className="column-picker-menu">
        {OPTIONAL_COLUMNS.map((c) => (
          <label className="toggle" key={c.key}>
            <input
              type="checkbox"
              checked={columns.includes(c.key)}
              onChange={() =>
                onChange(columns.includes(c.key) ? columns.filter((k) => k !== c.key) : [...columns, c.key])
              }
            />
            {c.label}
          </label>
        ))}
      </div>
    </details>
  );
}
