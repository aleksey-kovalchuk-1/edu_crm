import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import {
  useNotificationPreferences, useSavePreferences, useSetPause, type NotificationPreferences, type PauseDuration,
} from "../../api/notifications";
import { formatDateTime } from "../../lib/format";

const PAUSE_OPTIONS: { value: Exclude<PauseDuration, "off">; label: string }[] = [
  { value: "1h", label: "На 1 час" },
  { value: "tomorrow", label: "До завтра (08:00)" },
  { value: "1w", label: "На неделю" },
  { value: "forever", label: "До выключения" },
];

/** A pause "until turned off" is stored as a far-future moment (year 9999). */
const isIndefinite = (until: string) => new Date(until).getUTCFullYear() >= 9999;
const isActive = (until: string | null): until is string => Boolean(until) && new Date(until as string) > new Date();

export function SettingsNotificationsPage() {
  const prefs = useNotificationPreferences();
  if (prefs.isError) {
    return <section className="panel"><p className="danger" role="alert">{errorText(prefs.error)}</p></section>;
  }
  if (!prefs.data) {
    return <section className="panel"><p className="muted">Загрузка…</p></section>;
  }
  return (
    <>
      <PausePanel pausedUntil={prefs.data.paused_until} />
      <PreferencesForm prefs={prefs.data} />
    </>
  );
}

function PausePanel({ pausedUntil }: { pausedUntil: string | null }) {
  const setPause = useSetPause();
  const [duration, setDuration] = useState<Exclude<PauseDuration, "off">>("1h");
  const paused = isActive(pausedUntil);

  return (
    <section className="panel" aria-labelledby="pause-title">
      <h2 id="pause-title">Пауза</h2>
      <p className="muted">
        Пока пауза действует, новые уведомления не создаются и не копятся. Отмеченные ниже события не меняются.
      </p>
      {paused ? (
        <div className="wizard-body">
          <p role="status">
            {isIndefinite(pausedUntil) ? "Уведомления приостановлены до выключения паузы" : `Уведомления приостановлены до ${formatDateTime(pausedUntil)}`}
          </p>
          <div className="wizard-actions">
            <button type="button" className="primary" disabled={setPause.isPending} onClick={() => setPause.mutate("off")}>
              Возобновить уведомления
            </button>
          </div>
        </div>
      ) : (
        <div className="form-row">
          <label>
            Длительность паузы
            <select value={duration} onChange={(e) => setDuration(e.target.value as Exclude<PauseDuration, "off">)}>
              {PAUSE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <button type="button" className="secondary" disabled={setPause.isPending} onClick={() => setPause.mutate(duration)}>
            Приостановить все уведомления
          </button>
        </div>
      )}
      {setPause.isError && <p className="danger" role="alert">{errorText(setPause.error)}</p>}
    </section>
  );
}

function PreferencesForm({ prefs }: { prefs: NotificationPreferences }) {
  const save = useSavePreferences();
  const initial = Object.fromEntries(prefs.groups.flatMap((g) => g.events.map((e) => [e.key, e.enabled])));
  const [state, setState] = useState<Record<string, boolean>>(initial);
  const [saved, setSaved] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const changed = Object.fromEntries(Object.entries(state).filter(([key, value]) => initial[key] !== value));
    setSaved(false);
    save.mutate(changed, { onSuccess: () => setSaved(true) });
  }

  return (
    <form className="panel" onSubmit={submit} aria-labelledby="events-title">
      <h2 id="events-title">События</h2>
      <p className="muted">Отмеченные события приходят уведомлением в колокольчик справа вверху.</p>
      <div className="wizard-body">
        {prefs.groups.map((group) => (
          <fieldset key={group.key} className="notification-group">
            <legend>{group.label}</legend>
            {group.events.map((e) => (
              <label key={e.key} className="checkbox-row">
                <input
                  type="checkbox"
                  checked={state[e.key]}
                  onChange={(ev) => { setState((s) => ({ ...s, [e.key]: ev.target.checked })); setSaved(false); }}
                />
                {e.label}
              </label>
            ))}
          </fieldset>
        ))}
        {save.isError && <p className="danger" role="alert">{errorText(save.error)}</p>}
        {saved && <p className="text-green" role="status">Настройки сохранены</p>}
        <div className="wizard-actions">
          <button className="primary" disabled={save.isPending}>{save.isPending ? "Сохраняем…" : "Сохранить"}</button>
        </div>
      </div>
    </form>
  );
}
