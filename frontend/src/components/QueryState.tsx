import type { ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import { errorText } from "../api/client";

/** The subset of a TanStack query result these helpers need. */
export interface QueryLike {
  isPending: boolean;
  isError: boolean;
  data: unknown;
  error: Error | null;
  refetch: () => Promise<unknown>;
}

export function ErrorAlert({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  return (
    <div className="error" role="alert">
      {errorText(error)}
      {onRetry && (
        <button onClick={onRetry}>
          <RefreshCw size={16} />
          Повторить
        </button>
      )}
    </div>
  );
}

const retryFailed = (queries: QueryLike[]) => () =>
  queries.filter((q) => q.isError).forEach((q) => void q.refetch());

/**
 * Loading or error UI while the page's queries have no data yet; null once
 * every query has data.
 */
export function queryFallback(queries: QueryLike[]): ReactNode | null {
  const failed = queries.find((q) => q.isError && q.data === undefined);
  if (failed) {
    return (
      <>
        <ErrorAlert error={failed.error} onRetry={retryFailed(queries)} />
        <div className="empty">
          Не удалось загрузить данные. Проверьте подключение и повторите
          загрузку.
        </div>
      </>
    );
  }
  if (queries.some((q) => q.isPending)) {
    return <div className="loading">Загружаем рабочее пространство…</div>;
  }
  return null;
}

/** Banner for a failed background refresh while older data is still shown. */
export function RefreshError({ queries }: { queries: QueryLike[] }) {
  const failed = queries.find((q) => q.isError);
  return failed ? (
    <ErrorAlert error={failed.error} onRetry={retryFailed(queries)} />
  ) : null;
}
