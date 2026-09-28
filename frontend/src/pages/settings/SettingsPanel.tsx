import type { FormEvent, ReactNode } from "react";

/**
 * One section of a Settings page: heading with a one-line purpose, optional actions on the right,
 * then the body. With `onSubmit` the section is the form itself.
 */
export function SettingsPanel({
  titleId,
  title,
  description,
  actions,
  onSubmit,
  children,
}: {
  titleId: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}) {
  const head = (
    <div className="section-head">
      <div>
        <h2 id={titleId}>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions}
    </div>
  );
  const body = <div className="settings-body">{children}</div>;
  return onSubmit ? (
    <form className="panel settings-panel" onSubmit={onSubmit} aria-labelledby={titleId} noValidate>
      {head}
      {body}
    </form>
  ) : (
    <section className="panel settings-panel" aria-labelledby={titleId}>
      {head}
      {body}
    </section>
  );
}
