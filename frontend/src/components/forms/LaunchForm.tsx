import type { FormEvent } from "react";
import { useItProducts, useUniversities } from "../../api/catalogs";
import { useCreateLaunch } from "../../api/queries";
import { FieldError, FormFooter, formText } from "./FormParts";

export function LaunchForm({ onDone }: { onDone: () => void }) {
  const universities = useUniversities();
  const products = useItProducts();
  const create = useCreateLaunch();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    create.mutate(
      {
        university_id: Number(f.get("university_id")),
        program: formText(f, "program"),
        product: formText(f, "product"),
        owner: formText(f, "owner"),
        students: Number(f.get("students")),
        deadline: formText(f, "deadline"),
        // Sent only when chosen: the catalog link is optional (D-221).
        ...(f.get("it_product_id") ? { it_product_id: Number(f.get("it_product_id")) } : {}),
      },
      { onSuccess: onDone },
    );
  }
  // A failed background refresh keeps the cached list usable, so only report
  // a universities error when there is nothing to choose from.
  const error =
    create.error ??
    (universities.data === undefined ? universities.error : null);
  return (
    <form onSubmit={submit}>
      <label>
        Учебное заведение
        <select name="university_id" required defaultValue="">
          <option value="" disabled>
            {universities.isPending ? "Загружаем реестр…" : "Выберите из реестра"}
          </option>
          {universities.data?.map((u) => (
            <option value={u.id} key={u.id}>
              {u.name}
            </option>
          ))}
        </select>
        <FieldError error={error} field="university_id" />
      </label>
      <label>
        Программа
        <input
          name="program"
          required
          maxLength={200}
          placeholder="Например, аналитика данных"
        />
        <FieldError error={error} field="program" />
      </label>
      <label>
        ИТ-продукт из справочника
        <select name="it_product_id" defaultValue="">
          <option value="">Не выбран</option>
          {products.data?.map((p) => (
            <option value={p.id} key={p.id}>
              {p.vendor} — {p.name}
            </option>
          ))}
        </select>
        <FieldError error={error} field="it_product_id" />
      </label>
      <label>
        Продукт / технологии
        <input
          name="product"
          required
          maxLength={200}
          placeholder="Например, PostgreSQL"
        />
        <FieldError error={error} field="product" />
      </label>
      <label>
        Ответственный
        <input
          name="owner"
          required
          maxLength={100}
          placeholder="Имя менеджера"
        />
        <FieldError error={error} field="owner" />
      </label>
      <div className="form-row">
        <label>
          Обучающиеся
          <input
            name="students"
            type="number"
            min="0"
            max="100000"
            required
            defaultValue="0"
          />
          <FieldError error={error} field="students" />
        </label>
        <label>
          Плановая дата запуска
          <input name="deadline" type="date" required />
          <FieldError error={error} field="deadline" />
        </label>
      </div>
      <FormFooter error={error} pending={create.isPending} onCancel={onDone} />
    </form>
  );
}
