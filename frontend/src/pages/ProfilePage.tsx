import { useState, type FormEvent } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { errorText } from "../api/client";
import { isPlausiblePhone, useRequestPhoneCode, useVerifyPhoneCode } from "../api/profile";
import { useSession } from "../app/AuthGate";
import { formatDateTime } from "../lib/format";

type Step = "view" | "phone" | "code";

const PHONE_FORMAT_HINT = "Форматы: +7XXXXXXXXXX, 8XXXXXXXXXX или 7XXXXXXXXXX.";
const PHONE_LOCAL_ERROR =
  "Введите номер телефона в формате +7XXXXXXXXXX, 8XXXXXXXXXX или 7XXXXXXXXXX";

/**
 * CRM-owned phone verification (D-161-D-163): request a code, then confirm it.
 * Every call here acts on the signed-in user's own account; there is no user id to pass.
 */
export function ProfilePage() {
  const { user } = useSession();
  const [step, setStep] = useState<Step>("view");
  const [pendingPhone, setPendingPhone] = useState("");
  const [phoneError, setPhoneError] = useState("");
  const [code, setCode] = useState("");

  const requestCode = useRequestPhoneCode();
  const verifyCode = useVerifyPhoneCode();
  const verified = Boolean(user.phone_verified_at);

  function openPhoneStep() {
    setPhoneError("");
    requestCode.reset();
    setStep("phone");
  }

  function submitPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const raw = new FormData(event.currentTarget).get("phone");
    const phone = typeof raw === "string" ? raw.trim() : "";
    if (!isPlausiblePhone(phone)) {
      setPhoneError(PHONE_LOCAL_ERROR);
      return;
    }
    setPhoneError("");
    requestCode.mutate(phone, {
      onSuccess: () => {
        setPendingPhone(phone);
        setCode("");
        verifyCode.reset();
        setStep("code");
      },
    });
  }

  function resend() {
    requestCode.mutate(pendingPhone, {
      onSuccess: () => {
        setCode("");
        verifyCode.reset();
      },
    });
  }

  function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    verifyCode.mutate(code, {
      onSuccess: () => {
        requestCode.reset();
        setStep("view");
      },
    });
  }

  return (
    <section className="panel" aria-labelledby="profile-phone-title">
      <div className="section-head">
        <div>
          <h2 id="profile-phone-title">Телефон</h2>
          <p>Используется только внутри CRM и нигде не публикуется.</p>
        </div>
      </div>

      {step === "view" && (
        <div className="wizard-body">
          <p className="profile-phone-status">
            {verified ? (
              <>
                <ShieldCheck size={16} className="text-green" aria-hidden="true" />
                <span>
                  Подтверждён: <strong>{user.phone}</strong>
                  {user.phone_verified_at && (
                    <span className="muted"> · {formatDateTime(user.phone_verified_at)}</span>
                  )}
                </span>
              </>
            ) : (
              <>
                <ShieldAlert size={16} aria-hidden="true" />
                <span className="muted">Номер телефона не подтверждён</span>
              </>
            )}
          </p>
          <div className="wizard-actions">
            <button type="button" className="secondary" onClick={openPhoneStep}>
              {verified ? "Изменить номер" : "Добавить номер"}
            </button>
          </div>
        </div>
      )}

      {step === "phone" && (
        <form onSubmit={submitPhone} className="wizard-body">
          <label>
            Номер телефона
            <input
              name="phone"
              type="tel"
              required
              autoFocus
              placeholder="+7XXXXXXXXXX"
              defaultValue={pendingPhone}
              aria-invalid={phoneError || requestCode.isError ? true : undefined}
            />
            {phoneError && <small className="field-error danger">{phoneError}</small>}
            {!phoneError && requestCode.isError && (
              <small className="field-error danger">{errorText(requestCode.error)}</small>
            )}
          </label>
          <small className="field-hint">{PHONE_FORMAT_HINT}</small>
          <div className="wizard-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => setStep("view")}
              disabled={requestCode.isPending}
            >
              Отмена
            </button>
            <button className="primary" disabled={requestCode.isPending}>
              {requestCode.isPending ? "Отправляем…" : "Отправить код"}
            </button>
          </div>
        </form>
      )}

      {step === "code" && (
        <form onSubmit={submitCode} className="wizard-body">
          <p className="step-note">
            Код отправлен на номер {pendingPhone}. Он действует 5 минут.
          </p>
          <label>
            Код из SMS
            <input
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              autoFocus
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              aria-invalid={verifyCode.isError ? true : undefined}
            />
            {verifyCode.isError && (
              <small className="field-error danger">{errorText(verifyCode.error)}</small>
            )}
          </label>
          {requestCode.isError && (
            <p className="danger" role="alert">
              {errorText(requestCode.error)}
            </p>
          )}
          <div className="wizard-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => setStep("phone")}
              disabled={verifyCode.isPending || requestCode.isPending}
            >
              Изменить номер
            </button>
            <button
              type="button"
              className="secondary"
              onClick={resend}
              disabled={requestCode.isPending || verifyCode.isPending}
            >
              {requestCode.isPending ? "Отправляем…" : "Отправить код ещё раз"}
            </button>
            <button className="primary" disabled={verifyCode.isPending}>
              {verifyCode.isPending ? "Проверяем…" : "Подтвердить"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
