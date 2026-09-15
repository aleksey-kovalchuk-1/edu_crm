import type { FormEvent } from "react";
import { useSaveUniversity } from "../../api/catalogs";
import type { University } from "../../api/types";
import { FieldError, FormFooter, formText } from "./FormParts";

/** Create (no `university`) or edit a university. */
export function UniversityForm({
  university,
  onDone,
}: {
  university?: University;
  onDone: () => void;
}) {
  const save = useSaveUniversity();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    save.mutate(
      {
        id: university?.id,
        data: {
          name: formText(f, "name"),
          short_name: formText(f, "short_name"),
          city: formText(f, "city"),
          region: formText(f, "region"),
          website: formText(f, "website").trim(),
        },
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
          defaultValue={university?.name}
          placeholder="Название учебного заведения"
        />
        <FieldError error={save.error} field="name" />
      </label>
      <label>
        Краткое название
        <input
          name="short_name"
          maxLength={50}
          defaultValue={university?.short_name}
          placeholder="Например, СТУ"
        />
        <FieldError error={save.error} field="short_name" />
      </label>
      <div className="form-row">
        <label>
          Город
          <input
            name="city"
            required
            maxLength={100}
            defaultValue={university?.city}
            placeholder="Город"
          />
          <FieldError error={save.error} field="city" />
        </label>
        <label>
          Регион
          <input
            name="region"
            maxLength={100}
            defaultValue={university?.region}
            placeholder="Регион"
          />
          <FieldError error={save.error} field="region" />
        </label>
      </div>
      <label>
        Сайт
        <input
          name="website"
          type="url"
          maxLength={255}
          defaultValue={university?.website}
          placeholder="https://"
        />
        <FieldError error={save.error} field="website" />
      </label>
      <FormFooter
        error={save.error}
        pending={save.isPending}
        onCancel={onDone}
        submitLabel={university ? "Сохранить" : "Создать"}
      />
    </form>
  );
}
