import { useId, useState, type FormEvent } from "react";
import {
  useCrmUsers,
  useItProducts,
  useSaveContract,
  useTransferStatuses,
  useUniversities,
  useUniversityContacts,
} from "../../api/catalogs";
import type { Contract, ContractInput } from "../../api/types";
import { useSession } from "../../app/AuthGate";
import { addOneYear, formatFullDate } from "../../lib/format";
import { ROLES, canEditCatalog } from "../../lib/user";
import { FieldError, FormFooter } from "./FormParts";

const DEFAULT_STATUS = "not_started";

/** Create (no `contract`) or edit a contract; `universityId` preselects the university. */
export function ContractForm({
  contract,
  universityId,
  onDone,
}: {
  contract?: Contract;
  universityId?: number;
  onDone: () => void;
}) {
  const { user } = useSession();
  const isEditor = canEditCatalog(user.roles);
  const hintId = useId();

  const [number, setNumber] = useState(contract?.contract_number ?? "");
  const [university, setUniversity] = useState(
    String(contract?.university.id ?? universityId ?? ""),
  );
  const [product, setProduct] = useState(String(contract?.it_product.id ?? ""));
  const [signedAt, setSignedAt] = useState(contract?.signed_at ?? "");
  const [validUntil, setValidUntil] = useState(contract?.valid_until ?? "");
  const [status, setStatus] = useState(contract?.transfer_status ?? "");
  const initialManager = String(contract?.manager?.id ?? "");
  const [manager, setManager] = useState(initialManager);
  const [contactIds, setContactIds] = useState<number[]>(
    contract?.contacts.map((c) => c.id) ?? [],
  );
  const [comment, setComment] = useState(contract?.comment ?? "");

  const universities = useUniversities();
  const products = useItProducts();
  const statuses = useTransferStatuses();
  const users = useCrmUsers(ROLES.user, isEditor);
  const universityNumber = university ? Number(university) : undefined;
  const contacts = useUniversityContacts(universityNumber);
  const save = useSaveContract();

  const statusList = statuses.data ?? [];
  const effectiveStatus =
    status ||
    (statusList.some((s) => s.value === DEFAULT_STATUS)
      ? DEFAULT_STATUS
      : (statusList[0]?.value ?? ""));

  // Keep the current values selectable even when they are inactive or out of the list.
  const universityOptions = (universities.data ?? []).map((u) => ({ id: u.id, name: u.name }));
  if (contract && !universityOptions.some((u) => u.id === contract.university.id))
    universityOptions.push(contract.university);
  const productOptions = (products.data ?? []).map((p) => ({
    id: p.id,
    label: `${p.vendor} — ${p.name}`,
  }));
  if (contract && !productOptions.some((p) => p.id === contract.it_product.id))
    productOptions.push({
      id: contract.it_product.id,
      label: `${contract.it_product.vendor} — ${contract.it_product.name}`,
    });
  const contactOptions = (contacts.data ?? []).map((c) => ({
    id: c.id,
    full_name: c.full_name,
  }));
  if (contract && universityNumber === contract.university.id)
    for (const c of contract.contacts)
      if (!contactOptions.some((o) => o.id === c.id)) contactOptions.push(c);

  const defaultValidity = signedAt ? addOneYear(signedAt) : "";

  function changeUniversity(value: string) {
    setUniversity(value);
    // Contacts belong to one university.
    setContactIds([]);
  }

  function toggleContact(id: number, checked: boolean) {
    setContactIds((ids) => (checked ? [...ids, id] : ids.filter((x) => x !== id)));
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data: ContractInput = {
      contract_number: number.trim(),
      university_id: Number(university),
      it_product_id: Number(product),
      signed_at: signedAt,
      transfer_status: effectiveStatus || undefined,
      contact_ids: contactIds,
      comment,
    };
    if (validUntil) data.valid_until = validUntil;
    // On edit an emptied date means "back to the default", which PATCH cannot express by omission.
    else if (contract && defaultValidity) data.valid_until = defaultValidity;
    if (isEditor && (contract ? manager !== initialManager : manager !== ""))
      data.manager_user_id = manager ? Number(manager) : null;
    save.mutate({ id: contract?.id, data }, { onSuccess: onDone });
  }

  const loadError =
    (universities.data === undefined && universities.error) ||
    (products.data === undefined && products.error) ||
    (statuses.data === undefined && statuses.error) ||
    null;
  const error = save.error ?? loadError;

  return (
    <form onSubmit={submit}>
      <label>
        Номер договора
        <input
          name="contract_number"
          required
          maxLength={100}
          value={number}
          onChange={(e) => setNumber(e.target.value)}
          placeholder="Например, Д-2026-001"
        />
        <FieldError error={save.error} field="contract_number" />
      </label>
      <label>
        Учебное заведение
        <select
          name="university_id"
          required
          value={university}
          onChange={(e) => changeUniversity(e.target.value)}
        >
          <option value="" disabled>
            {universities.isPending ? "Загружаем список…" : "Выберите учебное заведение"}
          </option>
          {universityOptions.map((u) => (
            <option value={u.id} key={u.id}>
              {u.name}
            </option>
          ))}
        </select>
        <FieldError error={save.error} field="university_id" />
      </label>
      <label>
        ИТ-продукт
        <select
          name="it_product_id"
          required
          value={product}
          onChange={(e) => setProduct(e.target.value)}
        >
          <option value="" disabled>
            {products.isPending ? "Загружаем список…" : "Выберите ИТ-продукт"}
          </option>
          {productOptions.map((p) => (
            <option value={p.id} key={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <FieldError error={save.error} field="it_product_id" />
      </label>
      <div className="form-row">
        <label>
          Дата подписания
          <input
            name="signed_at"
            type="date"
            required
            value={signedAt}
            onChange={(e) => setSignedAt(e.target.value)}
          />
          <FieldError error={save.error} field="signed_at" />
        </label>
        <div className="field-with-hint">
          <label>
            Действует до
            <input
              name="valid_until"
              type="date"
              min={signedAt || undefined}
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
              aria-describedby={hintId}
            />
            <FieldError error={save.error} field="valid_until" />
          </label>
          {/* Outside the label so it describes the field instead of naming it. */}
          <small className="field-hint" id={hintId} aria-live="polite">
            Необязательно: по умолчанию — через год после подписания
            {!validUntil && defaultValidity && (
              <>
                {" "}
                (<span data-testid="validity-preview">{formatFullDate(defaultValidity)}</span>)
              </>
            )}
          </small>
        </div>
      </div>
      <div className={isEditor ? "form-row" : undefined}>
        <label>
          Статус передачи
          <select
            name="transfer_status"
            value={effectiveStatus}
            onChange={(e) => setStatus(e.target.value)}
          >
            {!statusList.length && <option value="">Загружаем список…</option>}
            {statusList.map((s) => (
              <option value={s.value} key={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <FieldError error={save.error} field="transfer_status" />
        </label>
        {isEditor && (
          <label>
            Менеджер
            <select
              name="manager_user_id"
              value={manager}
              onChange={(e) => setManager(e.target.value)}
            >
              <option value="">
                {contract?.manager_name
                  ? `Не сопоставлен (${contract.manager_name})`
                  : "Не назначен"}
              </option>
              {contract?.manager &&
                !users.data?.some((u) => u.id === contract.manager?.id) && (
                  <option value={contract.manager.id}>{contract.manager.full_name}</option>
                )}
              {users.data?.map((u) => (
                <option value={u.id} key={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
            <FieldError error={save.error} field="manager_user_id" />
          </label>
        )}
      </div>
      <fieldset className="checkbox-group">
        <legend>Ответственные от вуза</legend>
        {!universityNumber ? (
          <p className="muted">Сначала выберите учебное заведение.</p>
        ) : contacts.isPending ? (
          <p className="muted">Загружаем контакты…</p>
        ) : contactOptions.length ? (
          contactOptions.map((c) => (
            <label className="checkbox" key={c.id}>
              <input
                type="checkbox"
                checked={contactIds.includes(c.id)}
                onChange={(e) => toggleContact(c.id, e.target.checked)}
              />
              {c.full_name}
            </label>
          ))
        ) : (
          <p className="muted">У учебного заведения нет активных контактов.</p>
        )}
        <FieldError error={save.error} field="contact_ids" />
      </fieldset>
      <label>
        Комментарий
        <textarea
          name="comment"
          rows={3}
          maxLength={2000}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <FieldError error={save.error} field="comment" />
      </label>
      <FormFooter
        error={error}
        pending={save.isPending}
        onCancel={onDone}
        submitLabel={contract ? "Сохранить" : "Создать"}
      />
    </form>
  );
}
