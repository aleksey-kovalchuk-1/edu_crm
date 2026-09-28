import { useEffect, useId, useRef } from "react";

export interface FieldProblem {
  /** The id of the invalid field, so the link can move focus to it. */
  id: string;
  label: string;
  message: string;
}

const fields = (n: number) => {
  const tens = n % 100;
  const ones = n % 10;
  if (tens >= 11 && tens <= 14) return "полей";
  if (ones === 1) return "поле";
  if (ones >= 2 && ones <= 4) return "поля";
  return "полей";
};

/**
 * Shown after a failed save, above the form: takes focus once per new set of errors and links each
 * problem to its field. Inline field errors stay in place (it complements, not replaces, them).
 */
export function ErrorSummary({ errors }: { errors: FieldProblem[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const signature = errors.map((e) => `${e.id}:${e.message}`).join("|");
  useEffect(() => {
    if (signature) ref.current?.focus();
  }, [signature]);
  if (!errors.length) return null;
  return (
    <div ref={ref} className="notice notice-error error-summary" role="group" aria-labelledby={titleId} tabIndex={-1}>
      <div className="notice-text">
        <strong id={titleId}>
          Исправьте {errors.length} {fields(errors.length)}
        </strong>
        <ul>
          {errors.map((e) => (
            <li key={e.id}>
              <a
                href={`#${e.id}`}
                onClick={(event) => {
                  event.preventDefault();
                  document.getElementById(e.id)?.focus();
                }}
              >
                {e.label}: {e.message}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
