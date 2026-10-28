import { Check, Copy, AlertCircle } from "lucide-react";
import { useId, useState } from "react";
import type { ChatResponse } from "../types";

// Fixed user-facing summaries; raw legacy messages and diagnostic codes stay in details.
const ERROR_SUMMARIES: Record<string, string> = {
  timeout: "Dịch vụ AI chưa phản hồi kịp. Bạn có thể thử lại sau.",
  connection_failure: "Chưa thể kết nối dịch vụ AI. Bạn có thể thử lại sau.",
  transient_unavailable: "Dịch vụ AI tạm thời không khả dụng. Dữ liệu của bạn vẫn được giữ.",
  quota_or_rate_limit: "Dịch vụ AI đang giới hạn lượt sử dụng. Vui lòng thử lại sau.",
  authentication_failed: "Chưa thể truy cập dịch vụ AI. Cần quản trị viên kiểm tra cấu hình.",
  permission_denied: "Dịch vụ AI chưa cho phép truy cập. Cần quản trị viên kiểm tra quyền sử dụng.",
  authentication_or_permission: "Chưa thể truy cập dịch vụ AI. Cần quản trị viên kiểm tra quyền sử dụng.",
  payment_required: "Dịch vụ AI yêu cầu quản trị viên kiểm tra hạn mức thanh toán.",
  resource_not_found: "Chưa tìm thấy tài nguyên AI được yêu cầu. Cần quản trị viên kiểm tra cấu hình.",
  insufficient_evidence: "Chưa đủ bằng chứng từ dữ liệu và tài liệu để kết luận chính xác.",
  provider_disabled: "Chức năng AI chưa được quản trị viên cho phép sử dụng.",
  configuration: "Chức năng AI chưa được cấu hình đầy đủ.",
};

export function ErrorDetails({ response, text }: { response?: ChatResponse; text: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const id = useId();
  const context = response?.error_context;
  const summary = ERROR_SUMMARIES[context?.error_category ?? ""]
    ?? "Chưa thể xử lý câu hỏi này chính xác. Dữ liệu của bạn vẫn được giữ.";
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
    <p className="message-text" role="alert">{summary}</p>
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
