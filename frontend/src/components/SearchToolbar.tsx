import type { ReactNode } from "react";
import { Search } from "lucide-react";

export function SearchToolbar({
  search,
  onSearch,
  count,
  placeholder = "Поиск по названию, городу или ответственному",
  children,
}: {
  search: string;
  onSearch: (value: string) => void;
  count?: number;
  placeholder?: string;
  children?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <label className="search">
        <Search size={18} />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={placeholder}
          aria-label="Поиск"
        />
      </label>
      {children}
      {count !== undefined && <span className="muted">{count} записей</span>}
    </div>
  );
}
