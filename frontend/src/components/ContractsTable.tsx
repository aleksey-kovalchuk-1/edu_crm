import { useState } from "react";
import { ChevronLeft, ChevronRight, Pencil } from "lucide-react";
import { PAGE_SIZE, useContracts } from "../api/catalogs";
import type { Contract, ContractFilters } from "../api/types";
import { formatFullDate } from "../lib/format";
import { ContractForm } from "./forms/ContractForm";
import { Modal } from "./Modal";
import { RefreshError, queryFallback } from "./QueryState";

function ValidityBadge({ contract }: { contract: Contract }) {
  if (contract.is_expired) return <span className="badge badge-danger">Истёк</span>;
  if (contract.expires_soon) return <span className="badge badge-warning">Истекает</span>;
  return null;
}

/** Paginated contracts table for the given filters, with an edit dialog. */
export function ContractsTable({
  filters,
  onOffset,
  hideUniversity = false,
  emptyText = "Договоры не найдены.",
}: {
  filters: ContractFilters;
  onOffset: (offset: number) => void;
  hideUniversity?: boolean;
  emptyText?: string;
}) {
  const contracts = useContracts(filters);
  const [editing, setEditing] = useState<Contract | null>(null);
  const fallback = queryFallback([contracts]);
  const page = contracts.data;
  if (fallback || !page) return fallback;

  const limit = page.limit || PAGE_SIZE;
  const from = page.total ? page.offset + 1 : 0;
  const to = page.offset + page.items.length;

  return (
    <>
      <RefreshError queries={[contracts]} />
      <div className="table-wrap" aria-busy={contracts.isFetching}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Номер</th>
              {!hideUniversity && <th scope="col">Учебное заведение</th>}
              <th scope="col">ИТ-продукт</th>
              <th scope="col">Подписан</th>
              <th scope="col">Действует до</th>
              <th scope="col">Статус передачи</th>
              <th scope="col">Менеджер</th>
              <th scope="col">Ответственные от вуза</th>
              <th scope="col">
                <span className="visually-hidden">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((c) => (
              <tr key={c.id}>
                <td>
                  <strong className="cell-title">{c.contract_number}</strong>
                  {c.comment && <small className="cell-note">{c.comment}</small>}
                </td>
                {!hideUniversity && <td>{c.university.name}</td>}
                <td>
                  {c.it_product.name}
                  <small>{c.it_product.vendor}</small>
                </td>
                <td>{formatFullDate(c.signed_at)}</td>
                <td>
                  <span className="validity">
                    {formatFullDate(c.valid_until)} <ValidityBadge contract={c} />
                  </span>
                </td>
                <td>{c.transfer_status_label}</td>
                <td>
                  {c.manager ? (
                    c.manager.full_name
                  ) : c.manager_name ? (
                    <>
                      {c.manager_name}
                      <small>не сопоставлен с пользователем</small>
                    </>
                  ) : (
                    <span className="muted">Не назначен</span>
                  )}
                </td>
                <td>
                  {c.contacts.length ? (
                    c.contacts.map((p) => p.full_name).join(", ")
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => setEditing(c)}
                    aria-label={`Изменить договор ${c.contract_number}`}
                    title="Изменить"
                  >
                    <Pencil size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!page.items.length && <p className="empty">{emptyText}</p>}
      </div>
      {page.total > limit || page.offset > 0 ? (
        <nav className="pagination" aria-label="Страницы договоров">
          <span className="muted">
            {from}–{to} из {page.total}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={page.offset === 0}
            onClick={() => onOffset(Math.max(0, page.offset - limit))}
          >
            <ChevronLeft size={16} /> Назад
          </button>
          <button
            type="button"
            className="secondary"
            disabled={to >= page.total}
            onClick={() => onOffset(page.offset + limit)}
          >
            Вперёд <ChevronRight size={16} />
          </button>
        </nav>
      ) : (
        <p className="table-total muted">Всего: {page.total}</p>
      )}
      {editing && (
        <Modal
          title={`Договор ${editing.contract_number}`}
          close={() => setEditing(null)}
          wide
        >
          <ContractForm contract={editing} onDone={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}
