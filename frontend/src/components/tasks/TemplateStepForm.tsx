import { useState, type FormEvent } from "react";
import { TASK_PRIORITY_LABELS, useAssignableUsers, type TaskPriority } from "../../api/tasks";
import { ASSIGNEE_RULE_LABELS, type AssigneeRule, type OffsetUnit, type TemplateStep, type TemplateStepInput } from "../../api/planTemplates";
import { FormFooter, formText } from "../forms/FormParts";

/** Shared by "add step" and "edit step" — same fields, only the submit handler differs. */
export function TemplateStepForm({
  initial,
  onSubmit,
  onCancel,
  pending,
  error,
}: {
  initial?: TemplateStep;
  onSubmit: (data: TemplateStepInput) => void;
  onCancel: () => void;
  pending: boolean;
  error: unknown;
}) {
  const [rule, setRule] = useState<AssigneeRule>(initial?.assignee_rule ?? "university_manager");
  const users = useAssignableUsers();

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const deadline = formText(f, "deadline_offset_days");
    const userId = formText(f, "assignee_rule_user_id");
    onSubmit({
      title: formText(f, "title"),
      description: formText(f, "description"),
      assignee_rule: rule,
      assignee_rule_user_id: rule === "specific_user" && userId ? Number(userId) : null,
      start_offset_days: Number(formText(f, "start_offset_days") || 0),
      deadline_offset_days: deadline ? Number(deadline) : null,
      offset_unit: formText(f, "offset_unit") as OffsetUnit,
      priority: formText(f, "priority") as TaskPriority,
      approval_required: f.get("approval_required") === "on",
      is_optional: f.get("is_optional") === "on",
      checklist_items: formText(f, "checklist_items")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    });
  }

  return (
    <form onSubmit={submit}>
      <label>
        Название шага
        <input name="title" required maxLength={200} defaultValue={initial?.title} autoFocus />
      </label>
      <label>
        Описание
        <textarea name="description" rows={2} maxLength={2000} defaultValue={initial?.description} />
      </label>
      <div className="form-row">
        <label>
          Правило назначения
          <select name="assignee_rule" value={rule} onChange={(e) => setRule(e.target.value as AssigneeRule)}>
            {(Object.entries(ASSIGNEE_RULE_LABELS) as [AssigneeRule, string][]).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {rule === "specific_user" && (
          <label>
            Пользователь
            <select name="assignee_rule_user_id" defaultValue={initial?.assignee_rule_user_id ?? ""} required>
              <option value="" disabled>
                Выберите
              </option>
              {users.data?.map((u) => (
                <option value={u.id} key={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Приоритет
          <select name="priority" defaultValue={initial?.priority ?? "normal"}>
            {(Object.entries(TASK_PRIORITY_LABELS) as [TaskPriority, string][]).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>
          Начало, дней от старта плана
          <input type="number" name="start_offset_days" min={0} defaultValue={initial?.start_offset_days ?? 0} />
        </label>
        <label>
          Срок, дней от старта плана
          <input type="number" name="deadline_offset_days" min={0} defaultValue={initial?.deadline_offset_days ?? ""} />
        </label>
        <label>
          Единицы отсчёта
          <select name="offset_unit" defaultValue={initial?.offset_unit ?? "calendar"}>
            <option value="calendar">Календарные дни</option>
            <option value="business">Рабочие дни</option>
          </select>
        </label>
      </div>
      <label className="toggle">
        <input type="checkbox" name="approval_required" defaultChecked={initial?.approval_required} />
        Требуется согласование перед завершением
      </label>
      <label className="toggle">
        <input type="checkbox" name="is_optional" defaultChecked={initial?.is_optional} />
        Необязательный шаг (можно пропустить при запуске плана)
      </label>
      <label>
        Пункты чек-листа (по одному на строке)
        <textarea
          name="checklist_items"
          rows={3}
          defaultValue={initial?.checklist_items.map((i) => i.title).join("\n")}
        />
      </label>
      <FormFooter error={error} pending={pending} onCancel={onCancel} submitLabel={initial ? "Сохранить" : "Добавить шаг"} />
    </form>
  );
}
