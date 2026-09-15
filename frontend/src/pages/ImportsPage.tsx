import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ArrowLeft, CheckCircle2, FileSpreadsheet, RefreshCw, Upload } from "lucide-react";
import { ApiError, errorText } from "../api/client";
import {
  IMPORT_ACCEPT,
  formatFileSize,
  importFileProblem,
  isMappingError,
  useApplyImport,
  useCheckImport,
  useImportFields,
  useUploadImport,
  type ImportField,
  type ImportListItem,
  type ImportMapping,
  type ImportReport,
  type ImportUpload,
} from "../api/imports";
import { useSession } from "../app/AuthGate";
import { ImportDetailsModal, ImportHistory } from "../components/ImportHistory";
import { ImportRowsTable, ImportSummaryView } from "../components/ImportReport";
import { Modal } from "../components/Modal";
import { ErrorAlert, queryFallback } from "../components/QueryState";
import { fieldErrorMessage } from "../components/forms/FormParts";
import { formatNumber } from "../lib/format";
import { canImportCatalogs } from "../lib/user";

export const FORBIDDEN_TITLE = "Недостаточно прав";

export function ImportsPage() {
  const { user } = useSession();
  if (!canImportCatalogs(user.roles)) {
    return (
      <section className="panel">
        <div className="empty forbidden">
          <h2>{FORBIDDEN_TITLE}</h2>
          <p>
            Загрузка справочников доступна руководителю и администратору. Если вам нужен доступ,
            обратитесь к администратору CRM.
          </p>
        </div>
      </section>
    );
  }
  return <ImportWorkspace />;
}

type Step = 1 | 2 | 3 | 4;
const STEPS: { step: Step; label: string }[] = [
  { step: 1, label: "Файл" },
  { step: 2, label: "Сопоставление" },
  { step: 3, label: "Проверка" },
  { step: 4, label: "Применение" },
];

/** Mapping limited to existing headers, one header per field (first field wins). */
function prefillMapping(upload: ImportUpload): ImportMapping {
  const used = new Set<string>();
  const result: ImportMapping = {};
  for (const [field, header] of Object.entries(upload.mapping ?? {})) {
    const valid = header && upload.headers.includes(header) && !used.has(header);
    if (valid) used.add(header);
    result[field] = valid ? header : null;
  }
  return result;
}

const alreadyApplied = (error: unknown) => error instanceof ApiError && error.status === 409;

function ImportWorkspace() {
  const [step, setStep] = useState<Step>(1);
  const [upload, setUpload] = useState<ImportUpload | null>(null);
  const [mapping, setMapping] = useState<ImportMapping>({});
  const [checked, setChecked] = useState<ImportReport | null>(null);
  const [applied, setApplied] = useState<ImportReport | null>(null);
  const [missing, setMissing] = useState<ImportField[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [opened, setOpened] = useState<Pick<ImportListItem, "id" | "filename"> | null>(null);
  // Bumped when the mapping changes, so a late check result for an old mapping is ignored.
  const checkSeq = useRef(0);

  const fields = useImportFields();
  const uploadFile = useUploadImport();
  const check = useCheckImport();
  const apply = useApplyImport();

  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  const busy = uploadFile.isPending || check.isPending || apply.isPending;

  function start(next: ImportUpload) {
    checkSeq.current += 1;
    setUpload(next);
    setMapping(prefillMapping(next));
    setChecked(null);
    setApplied(null);
    setMissing([]);
    check.reset();
    apply.reset();
    setStep(next.status === "applied" ? 1 : 2);
  }

  function restart() {
    checkSeq.current += 1;
    setUpload(null);
    setMapping({});
    setChecked(null);
    setApplied(null);
    setMissing([]);
    uploadFile.reset();
    check.reset();
    apply.reset();
    setStep(1);
  }

  /** Mapping for every CRM field (null for fields not chosen). */
  const fullMapping = (): ImportMapping =>
    fields.data
      ? Object.fromEntries(fields.data.map((f) => [f.name, mapping[f.name] ?? null]))
      : mapping;

  function changeMapping(field: string, header: string | null) {
    if (header && Object.entries(mapping).some(([f, h]) => f !== field && h === header)) return;
    checkSeq.current += 1;
    setMapping((current) => ({ ...current, [field]: header }));
    setChecked(null);
    setMissing([]);
    check.reset();
    apply.reset();
  }

  function runCheck() {
    if (!upload || check.isPending) return;
    const absent = (fields.data ?? []).filter((f) => f.required && !mapping[f.name]);
    setMissing(absent);
    if (absent.length) return;
    const seq = ++checkSeq.current;
    setChecked(null);
    apply.reset();
    setStep(3);
    check.mutate(
      { id: upload.id, mapping: fullMapping() },
      {
        onSuccess: (report) => {
          if (seq === checkSeq.current) setChecked(report);
        },
      },
    );
  }

  function runApply() {
    if (!upload || apply.isPending) return;
    apply.mutate(
      { id: upload.id, mapping: fullMapping() },
      {
        onSuccess: (report) => {
          setApplied(report);
          setConfirming(false);
          setStep(4);
        },
        onError: (error) => {
          if (alreadyApplied(error)) setConfirming(false);
        },
      },
    );
  }

  const reachable: Record<Step, boolean> = {
    1: true,
    2: !!upload && !applied,
    3: !!upload && !applied && (!!checked || check.isPending || check.isError),
    4: !!applied,
  };

  return (
    <div className="imports-layout">
      <section className="panel import-wizard" aria-labelledby="import-step-title">
        <nav aria-label="Шаги загрузки">
          <ol className="stepper">
            {STEPS.map(({ step: s, label }) => (
              <li key={s}>
                <button
                  type="button"
                  className={[
                    "step",
                    s === step ? "current" : "",
                    s < step ? "done" : "",
                  ].join(" ").trim()}
                  aria-current={s === step ? "step" : undefined}
                  disabled={s !== step && (!reachable[s] || busy)}
                  onClick={() => setStep(s)}
                >
                  <span className="step-index" aria-hidden="true">
                    {s}
                  </span>
                  <span>
                    <span className="visually-hidden">Шаг {s}: </span>
                    {label}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <div className="wizard-body">
          <h2 id="import-step-title" ref={headingRef} tabIndex={-1} className="step-title">
            {STEPS[step - 1].label}
          </h2>

          {step === 1 && (
            <FileStep
              current={upload}
              pending={uploadFile.isPending}
              error={uploadFile.error}
              onChoose={() => uploadFile.reset()}
              onUpload={(file) => uploadFile.mutate(file, { onSuccess: start })}
              onContinue={() => setStep(2)}
              canContinue={reachable[2]}
            />
          )}

          {step === 2 &&
            upload &&
            (queryFallback([fields]) ??
              (fields.data && (
                <MappingStep
                  upload={upload}
                  fields={fields.data}
                  mapping={mapping}
                  missing={missing}
                  serverError={isMappingError(check.error) ? check.error : null}
                  pending={check.isPending}
                  onChange={changeMapping}
                  onCheck={runCheck}
                />
              )))}

          {step === 3 && upload && (
            <>
              {check.isPending && (
                <div className="loading" role="status">
                  Проверяем строки файла…
                </div>
              )}
              {check.isError &&
                (isMappingError(check.error) ? (
                  <MappingErrorAlert error={check.error} onBack={() => setStep(2)} />
                ) : (
                  <ErrorAlert error={check.error} onRetry={runCheck} />
                ))}
              {alreadyApplied(apply.error) && (
                <div className="error" role="alert">
                  <span>
                    Эта загрузка уже применена, повторно применить её нельзя. Итоговый отчёт
                    доступен в истории загрузок. (код {(apply.error as ApiError).code})
                  </span>
                  <button type="button" onClick={() => setOpened(upload)}>
                    Открыть отчёт
                  </button>
                </div>
              )}
              {checked && (
                <>
                  <p className="step-note">
                    Проверка ничего не записывает. Строки с ошибками и пропущенные строки при
                    применении не загружаются.
                  </p>
                  <ImportSummaryView summary={checked.summary} />
                  <ImportRowsTable report={checked} />
                  <div className="wizard-actions">
                    <button type="button" className="secondary" onClick={() => setStep(2)}>
                      <ArrowLeft size={16} /> Изменить сопоставление
                    </button>
                    <button type="button" className="secondary" onClick={runCheck} disabled={busy}>
                      <RefreshCw size={16} /> Проверить снова
                    </button>
                    <button
                      type="button"
                      className="primary"
                      disabled={busy || checked.summary.valid === 0 || alreadyApplied(apply.error)}
                      onClick={() => {
                        apply.reset();
                        setConfirming(true);
                      }}
                    >
                      Применить загрузку
                    </button>
                  </div>
                  {checked.summary.valid === 0 && (
                    <p className="step-note">
                      В файле нет корректных строк — исправьте ошибки в файле или сопоставление.
                    </p>
                  )}
                </>
              )}
            </>
          )}

          {step === 4 && applied && (
            <>
              <div className="notice-success" role="status">
                <CheckCircle2 size={18} />
                <span>
                  Загрузка «{upload?.filename}» применена: записано строк —{" "}
                  {formatNumber(applied.summary.valid)}.
                </span>
              </div>
              <ImportSummaryView summary={applied.summary} applied />
              <ImportRowsTable report={applied} />
              <div className="wizard-actions">
                <button type="button" className="primary" onClick={restart}>
                  <Upload size={16} /> Загрузить другой файл
                </button>
              </div>
            </>
          )}
        </div>
      </section>

      <ImportHistory onOpen={setOpened} />

      {confirming && upload && checked && (
        <Modal
          title="Применить загрузку?"
          close={() => {
            if (!apply.isPending) setConfirming(false);
          }}
        >
          <div className="confirm-body">
            <p>
              Файл «{upload.filename}». Будет записано строк: {formatNumber(checked.summary.valid)}
              {checked.summary.with_warnings > 0 &&
                `, из них с предупреждениями: ${formatNumber(checked.summary.with_warnings)}`}
              .
            </p>
            <p>
              Не будут загружены строки с ошибками: {formatNumber(checked.summary.invalid)}, пропущенные
              строки: {formatNumber(checked.summary.skipped)}.
            </p>
            <ImportSummaryView summary={checked.summary} />
            <p className="form-note">
              Корректные строки записываются одной транзакцией. Повторно применить эту загрузку
              будет нельзя.
            </p>
            {apply.error && !alreadyApplied(apply.error) ? (
              <p className="danger" role="alert">
                {errorText(apply.error)}
              </p>
            ) : null}
          </div>
          <div className="modal-actions">
            <button
              type="button"
              className="secondary"
              disabled={apply.isPending}
              onClick={() => setConfirming(false)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="primary"
              disabled={apply.isPending}
              aria-busy={apply.isPending}
              onClick={runApply}
            >
              {apply.isPending ? "Применяем…" : "Применить"}
            </button>
          </div>
        </Modal>
      )}

      {opened && (
        <ImportDetailsModal
          key={opened.id}
          item={opened}
          close={() => setOpened(null)}
          onContinue={(data) => {
            setOpened(null);
            start(data);
          }}
        />
      )}
    </div>
  );
}

function FileStep({
  current,
  pending,
  error,
  onChoose,
  onUpload,
  onContinue,
  canContinue,
}: {
  current: ImportUpload | null;
  pending: boolean;
  error: unknown;
  onChoose: () => void;
  onUpload: (file: File) => void;
  onContinue: () => void;
  canContinue: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState("");
  const [dragging, setDragging] = useState(false);
  const hintId = useId();
  const errorId = useId();

  function choose(next: File | undefined) {
    if (!next || pending) return;
    onChoose();
    const message = importFileProblem(next);
    setProblem(message ?? "");
    setFile(message ? null : next);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer?.files?.[0]);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (file && !pending) onUpload(file);
  }

  const serverMessage =
    fieldErrorMessage(error, "file") ??
    (error instanceof ApiError && (error.status === 413 || error.status === 415)
      ? error.message
      : undefined);
  const fileError = problem || (serverMessage && error instanceof ApiError
    ? `${serverMessage} (код ${error.code})`
    : "");

  return (
    <form onSubmit={submit} className="file-step">
      <p className="step-note">
        Загрузите реестр договоров в формате Excel. Данные читаются с первого листа; столбцы
        сопоставляются с полями CRM на следующем шаге, до проверки ничего не записывается.
      </p>
      {current && (
        <div className="current-file">
          <FileSpreadsheet size={18} />
          <span>
            Текущая загрузка: <strong>{current.filename}</strong>, строк данных:{" "}
            {formatNumber(current.row_count)}
          </span>
          {canContinue && (
            <button type="button" className="text-button" onClick={onContinue}>
              К сопоставлению
            </button>
          )}
        </div>
      )}
      <div
        className={dragging ? "dropzone dragging" : "dropzone"}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <FileSpreadsheet size={30} aria-hidden="true" />
        <p>Перетащите файл сюда или</p>
        <label className="secondary file-button">
          Выберите файл
          <input
            type="file"
            className="visually-hidden"
            accept={IMPORT_ACCEPT}
            disabled={pending}
            aria-describedby={fileError ? `${hintId} ${errorId}` : hintId}
            aria-invalid={fileError ? true : undefined}
            onChange={(e) => {
              choose(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
        <small id={hintId} className="field-hint">
          Формат .xls или .xlsx, размер до 10 МБ.
        </small>
        {file && (
          <p className="chosen-file">
            Выбран файл: <strong>{file.name}</strong> · {formatFileSize(file.size)}
          </p>
        )}
        {fileError && (
          <p id={errorId} className="field-error danger" role="alert">
            {fileError}
          </p>
        )}
      </div>
      {error && !serverMessage ? <ErrorAlert error={error} /> : null}
      <div className="wizard-actions">
        <button className="primary" disabled={!file || pending} aria-busy={pending}>
          <Upload size={16} />
          {pending ? "Загружаем…" : "Загрузить файл"}
        </button>
      </div>
    </form>
  );
}

function MappingErrorAlert({ error, onBack }: { error: ApiError; onBack?: () => void }) {
  const messages = (error.details ?? [])
    .filter((d) => d.field === "mapping" || d.field?.startsWith("mapping."))
    .map((d) => d.message)
    .filter(Boolean);
  return (
    <div className="error mapping-error" role="alert">
      <div>
        <strong>Сопоставление столбцов требует исправления (код {error.code})</strong>
        {messages.length > 0 && (
          <ul>
            {messages.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        )}
      </div>
      {onBack && (
        <button type="button" onClick={onBack}>
          <ArrowLeft size={16} /> Вернуться к сопоставлению
        </button>
      )}
    </div>
  );
}

const cellText = (value: string | number | boolean | null | undefined) =>
  value === null || value === undefined || value === "" ? "—" : String(value);

function MappingStep({
  upload,
  fields,
  mapping,
  missing,
  serverError,
  pending,
  onChange,
  onCheck,
}: {
  upload: ImportUpload;
  fields: ImportField[];
  mapping: ImportMapping;
  missing: ImportField[];
  serverError: ApiError | null;
  pending: boolean;
  onChange: (field: string, header: string | null) => void;
  onCheck: () => void;
}) {
  const baseId = useId();
  // Distinct, non-empty headers (a mapping refers to a header by its text).
  const headers = [...new Set(upload.headers.filter((h) => h && h.trim()))];
  const preview = upload.preview ?? [];
  const owners = new Map<string, string>();
  for (const [field, header] of Object.entries(mapping)) if (header) owners.set(header, field);
  const labelOf = (name: string) => fields.find((f) => f.name === name)?.label ?? name;
  const mappedCount = fields.filter((f) => mapping[f.name]).length;
  const missingNames = new Set(missing.map((f) => f.name));
  const sample = (header: string | null | undefined) => {
    if (!header || !preview.length) return "—";
    const index = upload.headers.indexOf(header);
    return index < 0 ? "—" : cellText(preview[0].cells[index]);
  };

  return (
    <>
      <p className="step-note">
        Файл «{upload.filename}»: заголовки в строке {upload.header_row}, строк данных —{" "}
        {formatNumber(upload.row_count)}. Сопоставлено полей: {mappedCount} из {fields.length}.
        Один столбец можно выбрать только для одного поля.
      </p>
      {serverError && <MappingErrorAlert error={serverError} />}
      {missing.length > 0 && (
        <div className="error" role="alert">
          Выберите столбцы для обязательных полей: {missing.map((f) => `«${f.label}»`).join(", ")}.
        </div>
      )}
      <div className="table-wrap">
        <table className="data-table mapping-table">
          <caption className="visually-hidden">Сопоставление полей CRM и столбцов файла</caption>
          <thead>
            <tr>
              <th scope="col">Поле CRM</th>
              <th scope="col">Столбец файла</th>
              <th scope="col">Значение в первой строке</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => {
              const id = `${baseId}-${f.name}`;
              const value = mapping[f.name] ?? "";
              return (
                <tr key={f.name} className={missingNames.has(f.name) ? "row-invalid" : undefined}>
                  <td>
                    <label htmlFor={id} className="cell-title">
                      {f.label}
                    </label>
                    {f.required && <small className="required-mark">обязательное поле</small>}
                  </td>
                  <td>
                    <select
                      id={id}
                      value={value}
                      disabled={pending}
                      aria-required={f.required}
                      aria-invalid={missingNames.has(f.name) || undefined}
                      onChange={(e) => onChange(f.name, e.target.value || null)}
                    >
                      <option value="">
                        {f.required ? "— выберите столбец —" : "— не загружать —"}
                      </option>
                      {headers.map((h) => {
                        const owner = owners.get(h);
                        const taken = !!owner && owner !== f.name;
                        return (
                          <option key={h} value={h} disabled={taken}>
                            {taken ? `${h} (выбран для «${labelOf(owner)}»)` : h}
                          </option>
                        );
                      })}
                    </select>
                  </td>
                  <td className="wrap">{sample(value)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h3 className="preview-title" id={`${baseId}-preview`}>
        Первые строки файла
      </h3>
      {preview.length ? (
        <div
          className="table-wrap preview-wrap"
          role="region"
          aria-labelledby={`${baseId}-preview`}
          tabIndex={0}
        >
          <table className="data-table preview-table">
            <thead>
              <tr>
                <th scope="col">Строка</th>
                {upload.headers.map((h, i) => (
                  <th scope="col" key={i}>
                    {h || "Без заголовка"}
                    {h && owners.has(h) && (
                      <small className="mapped-to">→ {labelOf(owners.get(h)!)}</small>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.map((row) => (
                <tr key={row.row_number}>
                  <td>{row.row_number}</td>
                  {upload.headers.map((_, i) => (
                    <td key={i}>{cellText(row.cells[i])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="step-note">Предпросмотр строк недоступен.</p>
      )}

      <div className="wizard-actions">
        <button type="button" className="primary" onClick={onCheck} disabled={pending} aria-busy={pending}>
          {pending ? "Проверяем…" : "Проверить"}
        </button>
      </div>
    </>
  );
}
