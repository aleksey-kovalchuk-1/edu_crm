import { useState } from "react";
import { useSearchParams } from "react-router";
import { Pencil, Plus } from "lucide-react";
import {
  useItDirections,
  useItProducts,
  useSaveItDirection,
  useSaveItProduct,
} from "../api/catalogs";
import type { ITDirection, ITProduct } from "../api/types";
import { useSession } from "../app/AuthGate";
import { ErrorAlert, RefreshError, queryFallback } from "../components/QueryState";
import { Modal } from "../components/Modal";
import { SearchToolbar } from "../components/SearchToolbar";
import { Tabs } from "../components/Tabs";
import { DirectionForm, ProductForm } from "../components/forms/CatalogForms";
import { canEditCatalog } from "../lib/user";
import { useDebouncedValue } from "../lib/useDebouncedValue";

const TABS = [
  { id: "directions", label: "ИТ-направления" },
  { id: "products", label: "ИТ-продукты" },
];

export function CatalogsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "products" ? "products" : "directions";
  const { user } = useSession();
  const canEdit = canEditCatalog(user.roles);
  return (
    <Tabs
      label="Справочники"
      tabs={TABS}
      selected={tab}
      onSelect={(id) => setParams(id === "directions" ? {} : { tab: id }, { replace: true })}
    >
      {tab === "directions" ? (
        <DirectionsTab key="directions" canEdit={canEdit} />
      ) : (
        <ProductsTab key="products" canEdit={canEdit} />
      )}
    </Tabs>
  );
}

function InactiveToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      Показать неактивные
    </label>
  );
}

function StatusCell({ active }: { active: boolean }) {
  return active ? (
    <span className="badge badge-3">Активно</span>
  ) : (
    <span className="badge badge-4">Неактивно</span>
  );
}

type Editing<T> = { record?: T } | null;

function DirectionsTab({ canEdit }: { canEdit: boolean }) {
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const q = useDebouncedValue(search);
  const directions = useItDirections({ q, include_inactive: showInactive });
  const toggle = useSaveItDirection();
  const [editing, setEditing] = useState<Editing<ITDirection>>(null);
  const list = directions.data;

  return (
    <>
      <SearchToolbar
        search={search}
        onSearch={setSearch}
        count={list?.length}
        placeholder="Поиск по названию направления"
      >
        <InactiveToggle checked={showInactive} onChange={setShowInactive} />
        {canEdit && (
          <button type="button" className="primary" onClick={() => setEditing({})}>
            <Plus size={16} /> Добавить направление
          </button>
        )}
      </SearchToolbar>
      {toggle.error ? <ErrorAlert error={toggle.error} /> : null}
      <section className="panel">
        {queryFallback([directions]) ??
          (list && (
            <>
              <RefreshError queries={[directions]} />
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Название</th>
                      <th scope="col">Описание</th>
                      <th scope="col">Статус</th>
                      {canEdit && (
                        <th scope="col">
                          <span className="visually-hidden">Действия</span>
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <strong className="cell-title">{d.name}</strong>
                        </td>
                        <td className="wrap">{d.description || <span className="muted">—</span>}</td>
                        <td>
                          <StatusCell active={d.is_active} />
                        </td>
                        {canEdit && (
                          <td className="row-actions">
                            <button
                              type="button"
                              className="icon-button"
                              aria-label={`Изменить направление ${d.name}`}
                              title="Изменить"
                              onClick={() => setEditing({ record: d })}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              type="button"
                              className="text-button"
                              disabled={toggle.isPending}
                              onClick={() =>
                                toggle.mutate({ id: d.id, data: { is_active: !d.is_active } })
                              }
                            >
                              {d.is_active ? "Деактивировать" : "Активировать"}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!list.length && <p className="empty">Направления не найдены.</p>}
              </div>
            </>
          ))}
      </section>
      {editing && (
        <Modal
          title={editing.record ? "Изменить направление" : "Новое ИТ-направление"}
          close={() => setEditing(null)}
        >
          <DirectionForm direction={editing.record} onDone={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}

function ProductsTab({ canEdit }: { canEdit: boolean }) {
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [directionId, setDirectionId] = useState("");
  const q = useDebouncedValue(search);
  const directions = useItDirections();
  const products = useItProducts({
    q,
    direction_id: directionId ? Number(directionId) : undefined,
    include_inactive: showInactive,
  });
  const toggle = useSaveItProduct();
  const [editing, setEditing] = useState<Editing<ITProduct>>(null);
  const list = products.data;

  return (
    <>
      <SearchToolbar
        search={search}
        onSearch={setSearch}
        count={list?.length}
        placeholder="Поиск по вендору или названию"
      >
        <label className="inline-select">
          <span>Направление</span>
          <select value={directionId} onChange={(e) => setDirectionId(e.target.value)}>
            <option value="">Все</option>
            {directions.data?.map((d) => (
              <option value={d.id} key={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <InactiveToggle checked={showInactive} onChange={setShowInactive} />
        {canEdit && (
          <button type="button" className="primary" onClick={() => setEditing({})}>
            <Plus size={16} /> Добавить продукт
          </button>
        )}
      </SearchToolbar>
      {toggle.error ? <ErrorAlert error={toggle.error} /> : null}
      <section className="panel">
        {queryFallback([products]) ??
          (list && (
            <>
              <RefreshError queries={[products]} />
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Вендор</th>
                      <th scope="col">Программное обеспечение</th>
                      <th scope="col">ИТ-направления</th>
                      <th scope="col">Статус</th>
                      {canEdit && (
                        <th scope="col">
                          <span className="visually-hidden">Действия</span>
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((p) => (
                      <tr key={p.id}>
                        <td>{p.vendor}</td>
                        <td>
                          <strong className="cell-title">{p.name}</strong>
                          {p.description && <small className="cell-note">{p.description}</small>}
                        </td>
                        <td>
                          <ul className="chips" aria-label="Направления">
                            {p.directions.map((d) => (
                              <li className="chip" key={d.id}>
                                {d.name}
                              </li>
                            ))}
                          </ul>
                          {!p.directions.length && <span className="muted">—</span>}
                        </td>
                        <td>
                          <StatusCell active={p.is_active} />
                        </td>
                        {canEdit && (
                          <td className="row-actions">
                            <button
                              type="button"
                              className="icon-button"
                              aria-label={`Изменить продукт ${p.vendor} ${p.name}`}
                              title="Изменить"
                              onClick={() => setEditing({ record: p })}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              type="button"
                              className="text-button"
                              disabled={toggle.isPending}
                              onClick={() =>
                                toggle.mutate({ id: p.id, data: { is_active: !p.is_active } })
                              }
                            >
                              {p.is_active ? "Деактивировать" : "Активировать"}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!list.length && <p className="empty">Продукты не найдены.</p>}
              </div>
            </>
          ))}
      </section>
      {editing && (
        <Modal
          title={editing.record ? "Изменить продукт" : "Новый ИТ-продукт"}
          close={() => setEditing(null)}
        >
          <ProductForm product={editing.record} onDone={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}
