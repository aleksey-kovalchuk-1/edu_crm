export const OPTIONAL_COLUMNS: { key: string; label: string }[] = [
  { key: "status", label: "Статус" },
  { key: "priority", label: "Приоритет" },
  { key: "deadline", label: "Срок" },
  { key: "creator", label: "Создатель" },
  { key: "assignees", label: "Исполнители" },
  { key: "university", label: "Учебное заведение" },
  { key: "created_at", label: "Дата создания" },
];

export const DEFAULT_COLUMNS = ["status", "priority", "deadline", "creator", "assignees", "university"];

/** Native <details> disclosure — keyboard-operable with no extra JS (spec: "configurable ... columns"). */
export function TaskColumnPicker({ columns, onChange }: { columns: string[]; onChange: (columns: string[]) => void }) {
  return (
    <details className="column-picker">
      <summary>Колонки</summary>
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
