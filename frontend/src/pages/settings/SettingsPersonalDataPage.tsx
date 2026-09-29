import { Download, FileText } from "lucide-react";
import { SettingsPanel } from "./SettingsPanel";

/**
 * Demo versions of the two policies (owner request 29 Sep, D-242). The .docx files ship with the API and are served
 * only to signed-in CRM users (GET /api/v1/documents/{slug}); the same-origin link sends the session cookie.
 */
const POLICIES = [
  {
    id: "personal-data-policy",
    title: "Политика в области обработки персональных данных",
    description: "Как UniCRM собирает, хранит и защищает персональные данные.",
  },
  {
    id: "information-security-policy",
    title: "Политика информационной безопасности",
    description: "Правила защиты информации и доступа к UniCRM.",
  },
] as const;

export function SettingsPersonalDataPage() {
  return (
    <>
      {POLICIES.map((policy) => (
        <SettingsPanel key={policy.id} titleId={`${policy.id}-title`} title={policy.title} description={policy.description}>
          <div className="policy-document">
            <span className="badge badge-warning">Демонстрационная версия документа</span>
            <a
              className="secondary policy-download"
              href={`/api/v1/documents/${policy.id}`}
              download
              aria-label={`Скачать документ (.docx): ${policy.title}`}
            >
              <FileText size={16} aria-hidden="true" />
              Скачать документ (.docx)
              <Download size={16} aria-hidden="true" />
            </a>
          </div>
        </SettingsPanel>
      ))}
    </>
  );
}
