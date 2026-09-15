import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export function Modal({
  title,
  close,
  wide = false,
  children,
}: {
  title: string;
  close: () => void;
  /** Wider dialog for long forms. */
  wide?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={close}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
      aria-label={title}
      className={wide ? "wide" : undefined}
    >
      <div className="modal">
        <div className="section-head">
          <h2>{title}</h2>
          <button type="button" className="icon-button" onClick={close} aria-label="Закрыть">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
