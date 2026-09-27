import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import {
  SENDER_STATUS_LABELS, useRequestSender, useSenders, useTestSend, useWithdrawRequest, type Sender,
} from "../../api/emailSenders";
import { useProfile, useUpdateProfile } from "../../api/profile";

/** The address university mail is sent from: pick a usable one, or request a personal one. */
export function SenderAddressPanel() {
  const profile = useProfile();
  const senders = useSenders();
  const update = useUpdateProfile();
  const requestSender = useRequestSender();
  const withdraw = useWithdrawRequest();
  const testSend = useTestSend();
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");

  const list = senders.data ?? [];
  const selectedId = profile.data?.email_sender_identity_id ?? null;
  const selected = list.find((s) => s.id === selectedId);
  const usable = list.filter((s) => s.usable);
  const ownNotUsable = list.filter((s) => !s.is_shared && !s.usable);
  const isOpen = (s: Sender) => s.is_active && (s.status === "pending_approval" || s.status === "awaiting_confirmation");
  const hasOpen = ownNotUsable.some(isOpen);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    requestSender.mutate(
      { email_address: address.trim(), display_name: displayName.trim() },
      { onSuccess: () => { setAddress(""); setDisplayName(""); } },
    );
  }

  return (
    <section className="panel" aria-labelledby="profile-sender-title">
      <div className="section-head">
        <div>
          <h2 id="profile-sender-title">Адрес отправителя</h2>
          <p>
            С этого адреса уходят письма вузам. Новый адрес одобряет руководитель или администратор, затем его
            нужно подтвердить по ссылке из письма.
          </p>
        </div>
      </div>
      <div className="wizard-body">
        {selectedId !== null && selected && !selected.usable && (
          <p className="danger" role="status">{selected.email_address} — недоступен. Выберите другой адрес.</p>
        )}
        <label>
          Отправлять от имени
          <select
            value={selected?.usable ? String(selectedId) : ""}
            disabled={update.isPending}
            onChange={(e) => update.mutate({ email_sender_identity_id: Number(e.target.value) || 0 })}
          >
            <option value="">Системный адрес UniCRM</option>
            {usable.map((s) => (
              <option key={s.id} value={s.id}>
                {s.display_name} &lt;{s.email_address}&gt;{s.is_shared ? " · общий" : ""}
              </option>
            ))}
          </select>
        </label>
        {update.isError && <p className="danger" role="alert">{errorText(update.error)}</p>}

        {ownNotUsable.map((s) => (
          <p key={s.id} className="sender-request">
            <strong>{s.email_address}</strong> — {s.is_active ? SENDER_STATUS_LABELS[s.status] : "Деактивирован"}
            {s.is_active && s.status === "rejected" && s.rejection_reason && (
              <span className="muted"> · Причина: {s.rejection_reason}</span>
            )}
            {isOpen(s) && (
              <button type="button" className="secondary" disabled={withdraw.isPending} onClick={() => withdraw.mutate(s.id)}>
                Отозвать заявку
              </button>
            )}
          </p>
        ))}

        {!hasOpen && (
          <form onSubmit={submit} className="form-row">
            <label>
              Новый адрес
              <input type="email" required maxLength={254} value={address} onChange={(e) => setAddress(e.target.value)}
                aria-invalid={requestSender.isError ? true : undefined} />
            </label>
            <label>
              Имя отправителя
              <input required maxLength={200} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
            <button className="primary" disabled={requestSender.isPending}>
              {requestSender.isPending ? "Отправляем…" : "Отправить на одобрение"}
            </button>
          </form>
        )}
        {requestSender.isError && <p className="danger" role="alert">{errorText(requestSender.error)}</p>}

        <div className="wizard-actions">
          <button type="button" className="secondary" disabled={testSend.isPending} onClick={() => testSend.mutate()}>
            {testSend.isPending ? "Отправляем…" : "Отправить тестовое письмо себе"}
          </button>
        </div>
        {testSend.data && <p role="status" className={testSend.data.delivered ? "text-green" : "muted"}>{testSend.data.message}</p>}
        {testSend.isError && <p className="danger" role="alert">{errorText(testSend.error)}</p>}
      </div>
    </section>
  );
}
