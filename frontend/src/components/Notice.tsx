import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";

export type NoticeTone = "info" | "success" | "warning" | "error";

const ICONS = { info: Info, success: CircleCheck, warning: TriangleAlert, error: CircleAlert };

/**
 * An inline notification (Rostelecom «Notification Inline»): icon + text on the tone's 10% container.
 * Errors and warnings are alerts, the rest polite status; `role` keeps an existing announcement where needed.
 */
export function Notice({
  tone,
  role,
  children,
}: {
  tone: NoticeTone;
  role?: "alert" | "status";
  children: ReactNode;
}) {
  const Icon = ICONS[tone];
  return (
    <div className={`notice notice-${tone}`} role={role ?? (tone === "error" || tone === "warning" ? "alert" : "status")}>
      <Icon size={20} aria-hidden="true" />
      <div className="notice-text">{children}</div>
    </div>
  );
}
