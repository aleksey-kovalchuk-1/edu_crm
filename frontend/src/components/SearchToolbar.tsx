import type { ReactNode } from "react";
import { Search } from "lucide-react";

export function SearchToolbar({
  search,
  onSearch,
  count,
  children,
}: {
  search: string;
  onSearch: (value: string) => void;
  count: number;
  children?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <label className="search">
        <Search size={18} />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Поиск по названию, городу или ответственному"
          aria-label="Поиск"
        />
      </label>
      {children}
      <span className="muted">{count} записей</span>
    </div>
  );
}
