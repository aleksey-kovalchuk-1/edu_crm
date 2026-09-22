export function SettingsPlaceholderPage({
  heading,
  subtitle,
}: {
  heading: string;
  subtitle: string;
}) {
  return (
    <section className="panel">
      <h2>{heading}</h2>
      <p className="muted">{subtitle}</p>
      <p className="muted">Появится в одном из следующих этапов работы над разделом «Настройки».</p>
    </section>
  );
}
