import { useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Pencil, Plus } from "lucide-react";
import {
  useSaveContact,
  useSaveUniversity,
  useUniversity,
  useUniversityContacts,
} from "../api/catalogs";
import type { University, UniversityContact } from "../api/types";
import { useSession } from "../app/AuthGate";
import { paths } from "../app/navigation";
import { ContractsTable } from "../components/ContractsTable";
import { ManagersDialog } from "../components/ManagersDialog";
import { Modal } from "../components/Modal";
import { ErrorAlert, RefreshError, queryFallback } from "../components/QueryState";
import { ContactForm } from "../components/forms/CatalogForms";
import { ContractForm } from "../components/forms/ContractForm";
import { UniversityForm } from "../components/forms/UniversityForm";
import { canEditCatalog } from "../lib/user";
import { WebsiteLink } from "./UniversitiesPage";

function BackLink() {
  return (
    <Link className="text-button back-link" to={paths.universities}>
      <ArrowLeft size={16} /> Все учебные заведения
    </Link>
  );
}

export function UniversityPage() {
  const id = Number(useParams().id);
  const university = useUniversity(Number.isInteger(id) ? id : -1);
  const fallback = queryFallback([university]);
  if (fallback) return fallback;
  const record = university.data;
  if (!record)
    return (
      <>
        <BackLink />
        <p className="empty panel empty-state">
          Учебное заведение не найдено или у вас нет к нему доступа.
        </p>
      </>
    );
  return (
    <>
      <RefreshError queries={[university]} />
      <UniversityDetail university={record} />
    </>
  );
}

function UniversityDetail({ university }: { university: University }) {
  const { user } = useSession();
  const canEdit = canEditCatalog(user.roles);
  const [dialog, setDialog] = useState<"edit" | "managers" | "contract" | null>(null);
  const [contractsOffset, setContractsOffset] = useState(0);
  const toggle = useSaveUniversity();
  const close = () => setDialog(null);

  return (
    <>
      <BackLink />
      {toggle.error ? <ErrorAlert error={toggle.error} /> : null}
      <section className="panel" aria-labelledby="university-title">
        <div className="section-head">
          <div>
            <h2 id="university-title">
              {university.name}
              {!university.is_active && (
                <span className="badge badge-4 inline-badge">Неактивно</span>
              )}
            </h2>
            <p>Карточка учебного заведения</p>
          </div>
          {canEdit && (
            <div className="head-actions">
              <button
                type="button"
                className="secondary"
                disabled={toggle.isPending}
                onClick={() =>
                  toggle.mutate({
                    id: university.id,
                    data: { is_active: !university.is_active },
                  })
                }
              >
                {university.is_active ? "Деактивировать" : "Активировать"}
              </button>
              <button type="button" className="secondary" onClick={() => setDialog("edit")}>
                <Pencil size={15} /> Изменить
              </button>
            </div>
          )}
        </div>
        <dl className="fields">
          <div>
            <dt>Краткое название</dt>
            <dd>{university.short_name || "—"}</dd>
          </div>
          <div>
            <dt>Город</dt>
            <dd>{university.city || "—"}</dd>
          </div>
          <div>
            <dt>Регион</dt>
            <dd>{university.region || "—"}</dd>
          </div>
          <div>
            <dt>Сайт</dt>
            <dd>{university.website ? <WebsiteLink website={university.website} /> : "—"}</dd>
          </div>
        </dl>
      </section>

      <div className="detail-columns">
        <section className="panel" aria-labelledby="managers-title">
          <div className="section-head">
            <div>
              <h2 id="managers-title">Ответственные от ИТ-школы</h2>
              <p>Менеджеры, которые ведут учебное заведение</p>
            </div>
            {canEdit && (
              <button type="button" className="secondary" onClick={() => setDialog("managers")}>
                <Pencil size={15} /> Изменить
              </button>
            )}
          </div>
          {university.managers.length ? (
            <ul className="people-list">
              {university.managers.map((m) => (
                <li key={m.id}>{m.full_name}</li>
              ))}
            </ul>
          ) : (
            <p className="empty">Ответственные не назначены.</p>
          )}
        </section>
        <ContactsSection universityId={university.id} />
      </div>

      <section className="panel" aria-labelledby="contracts-title">
        <div className="section-head">
          <div>
            <h2 id="contracts-title">Договоры</h2>
            <p>Договоры и лицензии этого учебного заведения</p>
          </div>
          <button type="button" className="secondary" onClick={() => setDialog("contract")}>
            <Plus size={15} /> Новый договор
          </button>
        </div>
        <ContractsTable
          filters={{ university_id: university.id, offset: contractsOffset }}
          onOffset={setContractsOffset}
          hideUniversity
          emptyText="Договоров пока нет."
        />
      </section>

      {dialog === "edit" && (
        <Modal title="Изменить учебное заведение" close={close}>
          <UniversityForm university={university} onDone={close} />
        </Modal>
      )}
      {dialog === "managers" && <ManagersDialog university={university} close={close} />}
      {dialog === "contract" && (
        <Modal title="Новый договор" close={close} wide>
          <ContractForm universityId={university.id} onDone={close} />
        </Modal>
      )}
    </>
  );
}

function ContactsSection({ universityId }: { universityId: number }) {
  const [showInactive, setShowInactive] = useState(false);
  const contacts = useUniversityContacts(universityId, { include_inactive: showInactive });
  const toggle = useSaveContact(universityId);
  const [editing, setEditing] = useState<{ record?: UniversityContact } | null>(null);
  const list = contacts.data;

  return (
    <section className="panel" aria-labelledby="contacts-title">
      <div className="section-head">
        <div>
          <h2 id="contacts-title">Ответственные от вуза</h2>
          <p>Контактные лица учебного заведения</p>
        </div>
        <div className="head-actions">
          <label className="toggle">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Показать неактивные
          </label>
          <button type="button" className="secondary" onClick={() => setEditing({})}>
            <Plus size={15} /> Добавить
          </button>
        </div>
      </div>
      {toggle.error ? <ErrorAlert error={toggle.error} /> : null}
      {queryFallback([contacts]) ??
        (list && list.length ? (
          <ul className="contact-list">
            {list.map((c) => (
              <li key={c.id} className={c.is_active ? undefined : "inactive"}>
                <div>
                  <strong>
                    {c.full_name}
                    {!c.is_active && <span className="badge badge-4 inline-badge">Неактивно</span>}
                  </strong>
                  {c.position && <small>{c.position}</small>}
                  <small>{[c.email, c.phone].filter(Boolean).join(" · ")}</small>
                  {c.comment && <small>{c.comment}</small>}
                </div>
                <div className="row-actions">
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Изменить контакт ${c.full_name}`}
                    title="Изменить"
                    onClick={() => setEditing({ record: c })}
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    type="button"
                    className="text-button"
                    disabled={toggle.isPending}
                    onClick={() => toggle.mutate({ id: c.id, data: { is_active: !c.is_active } })}
                  >
                    {c.is_active ? "Деактивировать" : "Активировать"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">Контакты не добавлены.</p>
        ))}
      {editing && (
        <Modal
          title={editing.record ? "Изменить контакт" : "Новый ответственный от вуза"}
          close={() => setEditing(null)}
        >
          <ContactForm
            universityId={universityId}
            contact={editing.record}
            onDone={() => setEditing(null)}
          />
        </Modal>
      )}
    </section>
  );
}
