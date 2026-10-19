import { ChevronUp, LogOut } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { SessionInfo } from "../api";

export function AccountMenu({ account, onLogout }: {
  account: SessionInfo["user"];
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const logout = useRef<HTMLButtonElement>(null);
  const id = useId();
  const name = account.display_name.trim() || account.email;
  const initials = name.split(/\s+/u).slice(0, 2).map((part) => Array.from(part)[0]).join("").toLocaleUpperCase("vi");

  useEffect(() => {
    if (!open) return;
    logout.current?.focus();
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return <div className="account-footer" ref={root} onBlurCapture={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    <button ref={trigger} className="account-trigger" type="button" aria-label="Mở menu tài khoản"
      title={`${name} · ${account.email}`} aria-haspopup="menu" aria-expanded={open}
      aria-controls={open ? id : undefined} onClick={() => setOpen((current) => !current)}
      onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          setOpen(true);
        }
      }}>
      <span className="account-avatar" aria-hidden="true">{initials}</span>
      <span className="account-details"><strong>{name}</strong><small>{account.email}</small></span>
      <ChevronUp className="account-chevron" size={16} aria-hidden="true" />
    </button>
    {open ? <div className="account-popover" id={id} role="menu" aria-label="Tài khoản"
      onKeyDown={(event) => {
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          logout.current?.focus();
        }
      }}>
      <div className="account-summary" role="presentation">
        <span className="account-avatar" aria-hidden="true">{initials}</span>
        <span className="account-details"><strong>{name}</strong><small>{account.email}</small></span>
      </div>
      <button ref={logout} role="menuitem" type="button" onClick={() => { setOpen(false); onLogout(); }}>
        <LogOut size={17} aria-hidden="true" />Đăng xuất
      </button>
    </div> : null}
  </div>;
}
