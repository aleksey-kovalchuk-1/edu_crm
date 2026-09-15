import { useState, type FormEvent } from "react";
import {
  useItDirections,
  useSaveContact,
  useSaveItDirection,
  useSaveItProduct,
} from "../../api/catalogs";
import type { ITDirection, ITProduct, UniversityContact } from "../../api/types";
import { FieldError, FormFooter, formText } from "./FormParts";

const submitLabel = (editing: boolean) => (editing ? "Сохранить" : "Создать");

export function DirectionForm({
  direction,
  onDone,
}: {
  direction?: ITDirection;
  onDone: () => void;
}) {
  const save = useSaveItDirection();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    save.mutate(
      {
        id: direction?.id,
        data: { name: formText(f, "name").trim(), description: formText(f, "description") },
      },
      { onSuccess: onDone },
    );
  }
  return (
    <form onSubmit={submit}>
      <label>
        Название
        <input
          name="name"
          required
          maxLength={100}
          defaultValue={direction?.name}
          placeholder="Например, DevOps"
        />
        <FieldError error={save.error} field="name" />
      </label>
      <label>
        Описание
        <textarea
          name="description"
          rows={3}
          maxLength={1000}
          defaultValue={direction?.description}
        />
        <FieldError error={save.error} field="description" />
      </label>
      <FormFooter
        error={save.error}
        pending={save.isPending}
        onCancel={onDone}
        submitLabel={submitLabel(!!direction)}
      />
    </form>
  );
}

export function ProductForm({
  product,
  onDone,
}: {
  product?: ITProduct;
  onDone: () => void;
}) {
  const save = useSaveItProduct();
  const directions = useItDirections();
  const [directionIds, setDirectionIds] = useState<number[]>(
    product?.directions.map((d) => d.id) ?? [],
  );
  // Directions already linked stay visible even if they were deactivated.
  const options = (directions.data ?? []).map((d) => ({ id: d.id, name: d.name }));
  for (const d of product?.directions ?? [])
    if (!options.some((o) => o.id === d.id)) options.push(d);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    save.mutate(
      {
        id: product?.id,
        data: {
          vendor: formText(f, "vendor").trim(),
          name: formText(f, "name").trim(),
          description: formText(f, "description"),
          direction_ids: directionIds,
        },
      },
      { onSuccess: onDone },
    );
  }
  const error = save.error ?? (directions.data === undefined ? directions.error : null);
  return (
    <form onSubmit={submit}>
      <div className="form-row">
        <label>
          Вендор
          <input
            name="vendor"
            required
            maxLength={200}
            defaultValue={product?.vendor}
            placeholder="Например, РТК ИТ"
          />
          <FieldError error={save.error} field="vendor" />
        </label>
        <label>
          Программное обеспечение
          <input
            name="name"
            required
            maxLength={200}
            defaultValue={product?.name}
            placeholder="Название продукта"
          />
          <FieldError error={save.error} field="name" />
        </label>
      </div>
      <label>
        Описание
        <textarea
          name="description"
          rows={3}
          maxLength={1000}
          defaultValue={product?.description}
        />
        <FieldError error={save.error} field="description" />
      </label>
      <fieldset className="checkbox-group">
        <legend>ИТ-направления</legend>
        {directions.isPending ? (
          <p className="muted">Загружаем направления…</p>
        ) : options.length ? (
          options.map((d) => (
            <label className="checkbox" key={d.id}>
              <input
                type="checkbox"
                checked={directionIds.includes(d.id)}
                onChange={(e) =>
                  setDirectionIds((ids) =>
                    e.target.checked ? [...ids, d.id] : ids.filter((x) => x !== d.id),
                  )
                }
              />
              {d.name}
            </label>
          ))
        ) : (
          <p className="muted">Направления ещё не добавлены.</p>
        )}
        <FieldError error={save.error} field="direction_ids" />
      </fieldset>
      <FormFooter
        error={error}
        pending={save.isPending}
        onCancel={onDone}
        submitLabel={submitLabel(!!product)}
      />
    </form>
  );
}

export function ContactForm({
  universityId,
  contact,
  onDone,
}: {
  universityId: number;
  contact?: UniversityContact;
  onDone: () => void;
}) {
  const save = useSaveContact(universityId);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    save.mutate(
      {
        id: contact?.id,
        data: {
          full_name: formText(f, "full_name").trim(),
          position: formText(f, "position"),
          email: formText(f, "email").trim(),
          phone: formText(f, "phone").trim(),
          comment: formText(f, "comment"),
        },
      },
      { onSuccess: onDone },
    );
  }
  return (
    <form onSubmit={submit}>
      <label>
        ФИО
        <input
          name="full_name"
          required
          maxLength={200}
          defaultValue={contact?.full_name}
          placeholder="Фамилия Имя Отчество"
          autoComplete="off"
        />
        <FieldError error={save.error} field="full_name" />
      </label>
      <label>
        Должность
        <input name="position" maxLength={200} defaultValue={contact?.position} />
        <FieldError error={save.error} field="position" />
      </label>
      <div className="form-row">
        <label>
          Электронная почта
          <input
            name="email"
            type="email"
            maxLength={255}
            defaultValue={contact?.email}
            autoComplete="off"
          />
          <FieldError error={save.error} field="email" />
        </label>
        <label>
          Телефон
          <input
            name="phone"
            type="tel"
            maxLength={50}
            defaultValue={contact?.phone}
            autoComplete="off"
          />
          <FieldError error={save.error} field="phone" />
        </label>
      </div>
      <label>
        Комментарий
        <textarea name="comment" rows={3} maxLength={2000} defaultValue={contact?.comment} />
        <FieldError error={save.error} field="comment" />
      </label>
      <FormFooter
        error={save.error}
        pending={save.isPending}
        onCancel={onDone}
        submitLabel={submitLabel(!!contact)}
      />
    </form>
  );
}
