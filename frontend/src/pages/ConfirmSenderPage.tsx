import { useSearchParams } from "react-router";
import { errorText } from "../api/client";
import { useConfirmSender } from "../api/emailSenders";

/**
 * Public (outside AuthGate): the mailed single-use link proves control of the mailbox. Confirming needs
 * a click, so mail scanners that pre-open links never confirm an address by accident.
 */
export function ConfirmSenderPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const confirm = useConfirmSender();

  return (
    <main className="auth-screen">
      <section className="auth-card">
        <h1>Подтверждение адреса отправителя</h1>
        {!token && <p className="danger">В ссылке нет кода подтверждения. Откройте ссылку из письма целиком.</p>}
        {token && !confirm.isSuccess && (
          <>
            <p>Нажмите кнопку, чтобы подтвердить, что этот почтовый ящик можно использовать как адрес отправителя UniCRM.</p>
            <button type="button" className="primary" disabled={confirm.isPending} onClick={() => confirm.mutate(token)}>
              {confirm.isPending ? "Подтверждаем…" : "Подтвердить"}
            </button>
          </>
        )}
        {confirm.isSuccess && (
          <p className="text-green" role="status">Адрес {confirm.data.email_address} подтверждён. Окно можно закрыть.</p>
        )}
        {confirm.isError && <p className="danger" role="alert">{errorText(confirm.error)}</p>}
      </section>
    </main>
  );
}
