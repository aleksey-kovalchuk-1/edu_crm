import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import {
  useNotificationPreferences, useSavePreferences, useSetPause, type NotificationPreferences, type PauseDuration,
} from "../../api/notifications";
import { Notice } from "../../components/Notice";
import { ErrorAlert } from "../../components/QueryState";
import { formatDateTime } from "../../lib/format";
import { SettingsPanel } from "./SettingsPanel";

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
    return <section className="panel settings-panel"><ErrorAlert error={prefs.error} onRetry={() => void prefs.refetch()} /></section>;
  }
  if (!prefs.data) {
    return <section className="panel settings-panel"><div className="loading" role="status">Загружаем настройки уведомлений…</div></section>;
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
    <SettingsPanel
      titleId="pause-title"
      title="Пауза"
      description="Пока пауза действует, новые уведомления не создаются и не копятся. Отмеченные ниже события не меняются."
    >
      {paused ? (
        <>
          <Notice tone="warning" role="status">
            {isIndefinite(pausedUntil) ? "Уведомления приостановлены до выключения паузы" : `Уведомления приостановлены до ${formatDateTime(pausedUntil)}`}
          </Notice>
          <div className="wizard-actions">
            <button type="button" className="primary" disabled={setPause.isPending} onClick={() => setPause.mutate("off")}>
              Возобновить уведомления
            </button>
          </div>
        </>
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
      {setPause.isError && <Notice tone="error">{errorText(setPause.error)}</Notice>}
    </SettingsPanel>
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
    <SettingsPanel
      titleId="events-title"
      title="События"
      description="Отмеченные события приходят уведомлением в колокольчик справа вверху."
      onSubmit={submit}
    >
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
        {save.isError && <Notice tone="error">{errorText(save.error)}</Notice>}
        {saved && <Notice tone="success">Настройки сохранены</Notice>}
        <div className="wizard-actions">
          <button className="primary" disabled={save.isPending}>{save.isPending ? "Сохраняем…" : "Сохранить"}</button>
        </div>
    </SettingsPanel>
  );
}
