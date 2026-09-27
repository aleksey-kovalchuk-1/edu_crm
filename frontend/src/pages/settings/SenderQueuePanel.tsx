import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import {
  SENDER_STATUS_LABELS, useApproveSender, useCreateSharedSender, useDeactivateSender, useRejectSender,
  useResendConfirmation, useSenderQueue, useSenders,
} from "../../api/emailSenders";
import { formatDateTime } from "../../lib/format";

/** Supervisor/admin: approve or reject sender address requests, and manage shared addresses. */
export function SenderQueuePanel() {
  const queue = useSenderQueue();
  const senders = useSenders();
  const approve = useApproveSender();
  const reject = useRejectSender();
  const resend = useResendConfirmation();
  const create = useCreateSharedSender();
  const deactivate = useDeactivateSender();
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [notice, setNotice] = useState("");

  const actionError = approve.error ?? reject.error ?? resend.error ?? create.error ?? deactivate.error;
  const shared = (senders.data ?? []).filter((s) => s.is_shared);

  function confirmReject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rejecting === null) return;
    reject.mutate({ id: rejecting, reason: reason.trim() }, {
      onSuccess: () => { setRejecting(null); setReason(""); setNotice("Заявка отклонена."); },
    });
  }

  function addShared(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate({ email_address: address.trim(), display_name: displayName.trim() }, {
      onSuccess: (sender) => {
        setAddress("");
        setDisplayName("");
        setNotice(`На ${sender.email_address} отправлено письмо подтверждения.`);
      },
    });
  }

  return (
    <>
      <section className="panel" aria-labelledby="sender-queue-title">
        <h2 id="sender-queue-title">Заявки на адреса отправителей</h2>
        {queue.isPending && <p className="muted">Загрузка…</p>}
        {queue.isError && <p className="danger" role="alert">{errorText(queue.error)}</p>}
        {queue.data?.length === 0 && <p className="muted">Новых заявок нет.</p>}
        <ul className="sender-queue">
          {queue.data?.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.email_address}</strong> · {item.display_name} · {item.is_shared ? "общий" : item.requested_by}
                {item.requested_at && <span className="muted"> · {formatDateTime(item.requested_at)}</span>}
                <span className="muted"> · {SENDER_STATUS_LABELS[item.status]}</span>
              </div>
              {item.status === "pending_approval" && rejecting !== item.id && (
                <div className="wizard-actions">
                  <button type="button" className="primary" aria-label={`Одобрить ${item.email_address}`}
                    disabled={approve.isPending}
                    onClick={() => approve.mutate(item.id, { onSuccess: (d) => setNotice(d.message) })}>
                    Одобрить
                  </button>
                  <button type="button" className="secondary" aria-label={`Отклонить ${item.email_address}`}
                    onClick={() => { setRejecting(item.id); setReason(""); }}>
                    Отклонить
                  </button>
                </div>
              )}
              {item.status === "awaiting_confirmation" && (
                <button type="button" className="secondary" disabled={resend.isPending}
                  onClick={() => resend.mutate(item.id, { onSuccess: (d) => setNotice(d.message) })}>
                  Отправить письмо ещё раз
                </button>
              )}
              {rejecting === item.id && (
                <form onSubmit={confirmReject} className="form-row">
                  <label>
                    Причина отказа
                    <input maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
                  </label>
                  <button className="primary" disabled={reject.isPending}>Подтвердить отказ</button>
                  <button type="button" className="secondary" onClick={() => setRejecting(null)}>Отмена</button>
                </form>
              )}
            </li>
          ))}
        </ul>
        {notice && <p role="status" className="muted">{notice}</p>}
        {actionError && <p className="danger" role="alert">{errorText(actionError)}</p>}
      </section>

      <section className="panel" aria-labelledby="shared-senders-title">
        <h2 id="shared-senders-title">Общие адреса</h2>
        <p className="muted">Подтверждённые адреса, которые может выбрать любой пользователь. Новый адрес становится доступен после подтверждения по ссылке из письма.</p>
        <ul className="sender-queue">
          {shared.map((s) => (
            <li key={s.id}>
              <strong>{s.email_address}</strong> · {s.display_name}
              <button type="button" className="secondary" aria-label={`Деактивировать ${s.email_address}`}
                disabled={deactivate.isPending} onClick={() => deactivate.mutate(s.id)}>
                Деактивировать
              </button>
            </li>
          ))}
        </ul>
        <form onSubmit={addShared} className="form-row">
          <label>
            Адрес
            <input type="email" required maxLength={254} value={address} onChange={(e) => setAddress(e.target.value)} />
          </label>
          <label>
            Имя отправителя
            <input required maxLength={200} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <button className="primary" disabled={create.isPending}>Добавить общий адрес</button>
        </form>
      </section>
    </>
  );
}
