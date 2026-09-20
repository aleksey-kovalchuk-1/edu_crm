import { forwardRef } from "react";
import { Filter } from "lucide-react";

/** Opens the filter dialog (TaskFilterDialog); visually secondary to the primary "Создать задачу"
 * action, with a small badge for how many filter dimensions are currently applied. */
export const TaskFilterButton = forwardRef<HTMLButtonElement, { count: number; onClick: () => void }>(
  function TaskFilterButton({ count, onClick }, ref) {
    return (
      <button ref={ref} type="button" className="secondary filter-toggle" onClick={onClick} aria-haspopup="dialog">
        <Filter size={16} />
        Фильтры
        {count > 0 && (
          <span className="filter-count-badge" aria-label={`Применено фильтров: ${count}`}>
            {count}
          </span>
        )}
      </button>
    );
  },
);
