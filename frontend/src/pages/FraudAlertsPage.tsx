import { useState } from "react";
import { useFraudAlert, useFraudAlerts, useFraudStatus, useReviewFraudAlert,
  type AlertStatus, type ResolutionCode } from "../api/fraudAlerts";
import { useSession } from "../app/AuthGate";
import { ErrorAlert, queryFallback } from "../components/QueryState";
import { canEditCatalog } from "../lib/user";

const RULES: Record<string, string> = {
  application_number_conflict: "Конфликт номера заявки",
  learner_match_conflict: "Неоднозначное совпадение анкет",
  shared_contact: "Общий контакт",
  document_identifier_reuse: "Повтор документа",
  batch_repetition: "Повтор в файле",
  import_velocity: "Необычный объём загрузок",
};
const STATUS: Record<AlertStatus, string> = {
  open: "Открыт", in_review: "На проверке", cleared: "Проверен", confirmed: "Подтверждён проверкой",
};
const NEXT_STATUS: Record<AlertStatus, AlertStatus[]> = {
  open: ["in_review", "cleared", "confirmed"],
  in_review: ["open", "cleared", "confirmed"],
  cleared: ["in_review"],
  confirmed: ["in_review"],
};
const REASONS: { value: ResolutionCode; label: string }[] = [
  { value: "legitimate_shared_contact", label: "Допустимый общий контакт" },
  { value: "data_corrected", label: "Данные исправлены" },
  { value: "false_positive", label: "Ложный сигнал" },
  { value: "confirmed_by_review", label: "Подтверждено проверкой" },
  { value: "needs_more_information", label: "Нужны дополнительные сведения" },
];
const PRIORITY = { low: "Низкий", medium: "Средний", high: "Высокий" };
/** Record names for alerts about the archived learner, application and supplier pages (no page to open). */
const ARCHIVED_RECORD: Record<string, string> = {
  learner: "Анкета", course_application: "Заявка", vendor_contact: "Контакт поставщика",
};

export function FraudAlertsPage() {
  const { user } = useSession();
  if (!canEditCatalog(user.roles)) return <section className="panel"><p className="empty">Проверка сигналов доступна руководителю и администратору.</p></section>;
  return <FraudAlertsWorkspace />;
}

function FraudAlertsWorkspace() {
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [decision, setDecision] = useState<AlertStatus | "">("");
  const [reason, setReason] = useState<ResolutionCode | "">("");
  const queue = useFraudAlerts(status, priority);
  const system = useFraudStatus();
  const detail = useFraudAlert(selectedId);
  const review = useReviewFraudAlert();
  const alert = detail.data;
  const documentState = system.data?.document_match;
  async function saveDecision() {
    if (!alert || !decision) return;
    await review.mutateAsync({ id: alert.id, status: decision,
      resolution_code: reason || null, expected_updated_at: alert.updated_at });
    setDecision("");
    setReason("");
  }
  return <div className="customer-workspace">
    <section className="panel">
      <h2>Сигналы для проверки</h2>
      <p className="muted">Сигнал указывает на противоречие в данных и требует проверки человеком.</p>
      {documentState && documentState !== "active" ? <p className="form-note">Сравнение документов: {documentState === "needs_backfill"
        ? "нужен перенос ранее созданных анкет" : "ключ не настроен"}.</p> : null}
      <div className="customer-toolbar">
        <label>Статус <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">Все</option>{Object.entries(STATUS).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select></label>
        <label>Приоритет <select value={priority} onChange={(event) => setPriority(event.target.value)}>
          <option value="">Все</option>{Object.entries(PRIORITY).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select></label>
      </div>
      {queryFallback([queue]) ?? (queue.data?.length ? <div className="table-wrap"><table className="data-table"><thead><tr>
        <th scope="col">Сигнал</th><th scope="col">Приоритет</th><th scope="col">Статус</th><th scope="col">Создан</th>
      </tr></thead><tbody>{queue.data.map((item) => <tr key={item.id}>
        <td><button type="button" className="table-link" onClick={() => { setSelectedId(item.id); setDecision(""); setReason(""); }}>
          Сигнал {item.id}: {RULES[item.rule_code] ?? item.rule_code}</button></td>
        <td>{PRIORITY[item.priority]}</td><td>{STATUS[item.status]}</td>
        <td>{new Date(item.created_at).toLocaleString("ru-RU")}</td>
      </tr>)}</tbody></table></div> : <p className="empty">Сигналов по выбранным фильтрам нет.</p>)}
    </section>
    {selectedId !== null ? <section className="panel">
      <div className="section-head"><h2>Разбор сигнала {selectedId}</h2><button type="button" onClick={() => setSelectedId(null)}>Закрыть</button></div>
      {queryFallback([detail]) ?? (alert ? <>
        <p>{RULES[alert.rule_code] ?? alert.rule_code}. Приоритет: {PRIORITY[alert.priority]}. Статус: {STATUS[alert.status]}.</p>
        {alert.evidence_kind ? <p>Тип совпадения: {alert.evidence_kind === "snils" ? "СНИЛС" : "Паспорт"}.</p> : null}
        {alert.entity_type && alert.entity_id && ARCHIVED_RECORD[alert.entity_type] ?
          <p className="muted">{ARCHIVED_RECORD[alert.entity_type]} #{alert.entity_id} · раздел в архиве</p> : null}
        {alert.related_entity_id && alert.entity_type && ARCHIVED_RECORD[alert.entity_type] ?
          <p className="muted">Связанная запись #{alert.related_entity_id} · раздел в архиве</p> : null}
        <div className="customer-toolbar">
          <label>Решение <select value={decision} onChange={(event) => setDecision(event.target.value as AlertStatus | "")}>
            <option value="">Выберите</option>{Object.entries(STATUS).filter(([code]) => NEXT_STATUS[alert.status].includes(code as AlertStatus))
              .map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select></label>
          <label>Причина <select value={reason} onChange={(event) => setReason(event.target.value as ResolutionCode | "")}>
            <option value="">Выберите</option>{REASONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select></label>
          <button type="button" className="primary" disabled={!decision || (decision !== "open" && decision !== "in_review" && !reason) || review.isPending}
            onClick={() => void saveDecision()}>Сохранить решение</button>
        </div>
        {review.error ? <ErrorAlert error={review.error} /> : null}
      </> : null)}
    </section> : null}
  </div>;
}
