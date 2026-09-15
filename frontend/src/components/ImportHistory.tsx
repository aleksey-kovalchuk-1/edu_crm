import { useImport, useImports, type ImportListItem, type ImportUpload } from "../api/imports";
import { formatDateTime, formatNumber } from "../lib/format";
import { ImportRowsTable, ImportStatusBadge, ImportSummaryView } from "./ImportReport";
import { Modal } from "./Modal";
import { RefreshError, queryFallback } from "./QueryState";

function historyCounts(item: ImportListItem) {
  const s = item.summary;
  if (!s) return `Строк: ${formatNumber(item.row_count)}`;
  return `Строк: ${formatNumber(s.rows)} · корректных: ${formatNumber(s.valid)} · с ошибками: ${formatNumber(s.invalid)}`;
}

export function ImportHistory({ onOpen }: { onOpen: (item: ImportListItem) => void }) {
  const list = useImports();
  return (
    <section className="panel import-history" aria-labelledby="import-history-title">
      <div className="section-head">
        <div>
          <h2 id="import-history-title">История загрузок</h2>
          <p>Последние 20 загрузок</p>
        </div>
      </div>
      {queryFallback([list]) ??
        (list.data && (
          <>
            <RefreshError queries={[list]} />
            {list.data.length ? (
              <ul className="history-list">
                {list.data.map((item) => (
                  <li key={item.id}>
                    <button type="button" className="history-item" onClick={() => onOpen(item)}>
                      <span className="history-item-top">
                        <strong>{item.filename}</strong>
                        <ImportStatusBadge status={item.status} />
                      </span>
                      <span className="history-meta">
                        {item.created_by?.full_name ?? "Автор неизвестен"} ·{" "}
                        {formatDateTime(item.created_at)}
                      </span>
                      <span className="history-meta">{historyCounts(item)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty">Загрузок пока не было.</p>
            )}
          </>
        ))}
    </section>
  );
}

/** Details and report of one upload; an unapplied upload can be continued. */
export function ImportDetailsModal({
  item,
  close,
  onContinue,
}: {
  item: Pick<ImportListItem, "id" | "filename">;
  close: () => void;
  onContinue: (upload: ImportUpload) => void;
}) {
  const detail = useImport(item.id);
  const data = detail.data;
  return (
    <Modal title={`Загрузка «${item.filename}»`} close={close} wide>
      {queryFallback([detail]) ??
        (data && (
          <>
            <dl className="fields import-fields">
              <div>
                <dt>Статус</dt>
                <dd>
                  <ImportStatusBadge status={data.status} />
                </dd>
              </div>
              <div>
                <dt>Автор</dt>
                <dd>{data.created_by?.full_name ?? "—"}</dd>
              </div>
              <div>
                <dt>Загружен</dt>
                <dd>{formatDateTime(data.created_at)}</dd>
              </div>
              {data.applied_at && (
                <div>
                  <dt>Применён</dt>
                  <dd>{formatDateTime(data.applied_at)}</dd>
                </div>
              )}
              <div>
                <dt>Строк данных</dt>
                <dd>{formatNumber(data.row_count)}</dd>
              </div>
              <div>
                <dt>Строка заголовков</dt>
                <dd>{data.header_row}</dd>
              </div>
            </dl>
            {data.report ? (
              <>
                <h3 className="modal-subheading">Отчёт применения</h3>
                <ImportSummaryView summary={data.report.summary} applied />
                <ImportRowsTable report={data.report} />
              </>
            ) : data.status === "uploaded" ? (
              <>
                <p className="form-note">
                  Загрузка ещё не применена. Можно продолжить: проверить сопоставление столбцов и
                  применить данные.
                </p>
                <div className="modal-actions">
                  <button type="button" className="secondary" onClick={close}>
                    Закрыть
                  </button>
                  <button type="button" className="primary" onClick={() => onContinue(data)}>
                    Продолжить загрузку
                  </button>
                </div>
              </>
            ) : (
              <p className="form-note">Отчёт применения недоступен.</p>
            )}
          </>
        ))}
    </Modal>
  );
}
