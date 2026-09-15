import type { FormEvent } from "react";
import { useCreateUniversity } from "../../api/queries";
import { FieldError, FormFooter, formText } from "./FormParts";

export function UniversityForm({ onDone }: { onDone: () => void }) {
  const create = useCreateUniversity();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    create.mutate(
      {
        name: formText(f, "name"),
        city: formText(f, "city"),
        contact: formText(f, "contact"),
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
          maxLength={200}
          placeholder="Название учебного заведения"
        />
        <FieldError error={create.error} field="name" />
      </label>
      <label>
        Город
        <input name="city" required maxLength={100} placeholder="Город" />
        <FieldError error={create.error} field="city" />
      </label>
      <label>
        Контактное лицо
        <input name="contact" maxLength={200} placeholder="Имя координатора" />
        <FieldError error={create.error} field="contact" />
      </label>
      <FormFooter
        error={create.error}
        pending={create.isPending}
        onCancel={onDone}
      />
    </form>
  );
}
