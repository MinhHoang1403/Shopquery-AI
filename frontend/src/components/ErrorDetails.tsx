import { Check, Copy, AlertCircle } from "lucide-react";
import { useId, useState } from "react";
import type { ChatResponse } from "../types";

export function ErrorDetails({ response, text }: { response?: ChatResponse; text: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const id = useId();
  const context = response?.error_context;
  const code = context?.correlation_id && /^[a-f0-9]{32}$/.test(context.correlation_id)
    ? context.correlation_id : null;
  const fields = [
    ["Nhóm lỗi", context?.error_category], ["Giai đoạn", context?.origin_stage],
    ["Tuyến đã thử", context?.attempted_route], ["Model đã dùng", response?.used_model],
    ["Mã lý do", context?.reason_code], ["Nhánh kiểm tra", context?.validation_branch],
  ];
  async function copyCode() {
    if (!code) return;
    try { await navigator.clipboard.writeText(code); setCopied(true); } catch { setCopied(false); }
  }
  return <div className="error-details">
    <p className="message-text" role="alert">Chưa thể hoàn tất truy vấn này.</p>
    <button type="button" className="evidence-trigger" aria-expanded={open} aria-controls={id}
      onClick={() => setOpen(!open)}><AlertCircle size={15} />Chi tiết lỗi</button>
    {open ? <div className="error-detail-panel" id={id}>
      <p>{response?.error || text}</p>
      <dl>{fields.filter(([, value]) => value).map(([label, value]) =>
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {code ? <><p>Mã hỗ trợ: <code>{code}</code></p>
        <button type="button" className="evidence-trigger" onClick={copyCode}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Đã sao chép" : "Sao chép mã hỗ trợ"}</button></> : null}
    </div> : null}
  </div>;
}
