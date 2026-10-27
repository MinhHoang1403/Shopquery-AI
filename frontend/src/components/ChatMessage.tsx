import { AlertCircle, Database } from "lucide-react";
import type { ConversationEntry, RouteLabel } from "../types";
import { AssistantContent } from "./AssistantContent";
import { ResponseEvidence } from "./ResponseEvidence";
import { ErrorDetails } from "./ErrorDetails";

const ROUTE_LABELS: Record<RouteLabel, string> = {
  SQL: "SQL",
  RAG: "Tài liệu",
  HYBRID: "SQL + Tài liệu",
  UNSUPPORTED: "Chưa thể trả lời",
};

const MODEL_LABELS = { "inetcloud-knowledge": "iNetCloud Knowledge", gemini: "Gemini" };
const LEGACY_GENERIC_REFUSAL = "Bộ dữ liệu không có đủ loại nguồn để trả lời câu hỏi này. Nếu cần ghép hai bảng, hãy kiểm tra Quản lý dữ liệu → Liên kết bảng. JOIN v1 chỉ hỗ trợ hai bảng với quan hệ đã xác nhận và tổng hợp fact an toàn.";
const GENERIC_REFUSAL = "Mình chưa đủ thông tin để trả lời chính xác câu hỏi này. Bạn hãy kiểm tra dữ liệu hoặc liên kết bảng trong Quản lý dữ liệu nhé.";

export function ChatMessage({ entry }: { entry: ConversationEntry }) {
  const isUser = entry.role === "user";
  const isError = entry.role === "error";
  const text = !isUser && !isError && entry.response?.route === "UNSUPPORTED"
    && entry.text === LEGACY_GENERIC_REFUSAL ? GENERIC_REFUSAL : entry.text;

  return (
    <article className={`message message--${entry.role}`}>
      {!isUser ? (
        <div className="assistant-mark" aria-hidden="true">
          {isError ? <AlertCircle size={17} /> : <Database size={16} />}
        </div>
      ) : null}
      <div className="message-content">
        {!isUser ? (
          <div className="message-heading">
            <strong>ShopQuery AI</strong>
            {entry.response?.used_model ? (
              <span className="model-attribution">{MODEL_LABELS[entry.response.used_model]}</span>
            ) : null}
            {entry.response?.route ? (
              <span className="route-badge">{ROUTE_LABELS[entry.response.route]}</span>
            ) : null}
          </div>
        ) : null}
        {entry.response?.route === "HYBRID" ? (
          <p className={`verification-notice verification-notice--${entry.response.verification_status === "verified_classification" ? "verified" : "unverified"}`}>
            {entry.response.verification_status === "verified_classification" ? "Kết luận đã được xác minh"
              : entry.response.verification_status === "explanation" ? "Giải thích từ tài liệu"
              : "Chưa xác minh kết luận"}
          </p>
        ) : null}
        {isError ? <ErrorDetails response={entry.response} text={text} />
          : isUser ? <p className="message-text">{text}</p>
          : <AssistantContent text={text} hideTables={Boolean(entry.response?.rows.length)} />}
        {entry.response?.fallback_used ? (
          <p className="fallback-notice">{entry.response.used_model
            ? "Đã chuyển từ Knowledge sang Gemini để hoàn tất yêu cầu."
            : "Đã thử chuyển sang Gemini nhưng chưa thể hoàn tất câu trả lời."}</p>
        ) : null}
        {entry.response ? <ResponseEvidence response={entry.response} /> : null}
      </div>
    </article>
  );
}
