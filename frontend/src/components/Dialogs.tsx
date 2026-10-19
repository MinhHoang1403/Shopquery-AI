import { AlertTriangle, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

interface ModalProps {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
}

export function Modal({ title, description, children, onClose, className = "" }: ModalProps) {
  const dialog = useRef<HTMLElement | null>(null);
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement;
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex='0']") ?? []).filter((node) => !node.closest("[hidden]"));
    if (!dialog.current?.contains(document.activeElement)) focusable()[0]?.focus();
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key === "Tab") {
        const items = focusable();
        const current = items.indexOf(document.activeElement as HTMLElement);
        if (!items.length) { event.preventDefault(); dialog.current?.focus(); }
        else if (event.shiftKey && current <= 0) { event.preventDefault(); items.at(-1)?.focus(); }
        else if (!event.shiftKey && (current === -1 || current === items.length - 1)) { event.preventDefault(); items[0].focus(); }
      }
    }
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section ref={dialog} tabIndex={-1} aria-describedby={description ? "modal-description" : undefined} aria-labelledby="modal-title" aria-modal="true" className={`modal ${className}`} role="dialog">
        <div className="modal-header">
          <div><h2 id="modal-title">{title}</h2>{description ? <p id="modal-description">{description}</p> : null}</div>
          <button aria-label="Đóng" className="icon-button" onClick={onClose} type="button"><X size={19} /></button>
        </div>
        {children}
      </section>
    </div>
  );
}

interface RenameDialogProps {
  currentTitle: string;
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (title: string) => void;
}

export function RenameDialog({ currentTitle, saving, error, onClose, onSave }: RenameDialogProps) {
  const [title, setTitle] = useState(currentTitle);
  return (
    <Modal title="Đổi tên cuộc trò chuyện" onClose={onClose}>
      <form className="dialog-form" onSubmit={(event) => { event.preventDefault(); onSave(title); }}>
        <label htmlFor="conversation-title">Tên cuộc trò chuyện</label>
        <input autoFocus id="conversation-title" maxLength={120} onChange={(event) => setTitle(event.target.value)} value={title} />
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button className="secondary-button" disabled={saving} onClick={onClose} type="button">Hủy</button>
          <button className="primary-button" disabled={saving || !title.trim()} type="submit">{saving ? "Đang lưu…" : "Lưu tên"}</button>
        </div>
      </form>
    </Modal>
  );
}

interface ConfirmDialogProps {
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({ title, description, confirmLabel, danger, busy, onClose, onConfirm }: ConfirmDialogProps) {
  return (
    <Modal title={title} description={description} onClose={onClose}>
      <div className="confirm-symbol" aria-hidden="true"><AlertTriangle size={21} /></div>
      <div className="dialog-actions">
        <button className="secondary-button" disabled={busy} onClick={onClose} type="button">Hủy</button>
        <button className={danger ? "danger-button" : "primary-button"} disabled={busy} onClick={onConfirm} type="button">{busy ? "Đang xử lý…" : confirmLabel}</button>
      </div>
    </Modal>
  );
}
