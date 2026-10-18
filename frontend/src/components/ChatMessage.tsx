import { AlertCircle, Database } from "lucide-react";
import type { ConversationEntry, RouteLabel } from "../types";
import { ResponseEvidence } from "./ResponseEvidence";

const ROUTE_LABELS: Record<RouteLabel, string> = {
  SQL: "SQL",
  RAG: "Tài liệu",
  HYBRID: "SQL + Tài liệu",
  UNSUPPORTED: "Ngoài phạm vi",
};

const MODEL_LABELS = { "inetcloud-knowledge": "iNetCloud Knowledge", gemini: "Gemini" };

export function ChatMessage({ entry }: { entry: ConversationEntry }) {
  const isUser = entry.role === "user";
  const isError = entry.role === "error";

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
            <strong>{isError ? "Không thể xử lý" : "ShopQuery AI"}</strong>
            {entry.response?.used_model ? (
              <span className="model-attribution">{MODEL_LABELS[entry.response.used_model]}</span>
            ) : null}
            {entry.response?.route ? (
              <span className="route-badge">{ROUTE_LABELS[entry.response.route]}</span>
            ) : null}
          </div>
        ) : null}
        <p className="message-text">{entry.text}</p>
        {entry.response?.fallback_used ? (
          <p className="fallback-notice">{entry.response.used_model
            ? "Đã chuyển từ Knowledge sang Gemini do mô hình chính không khả dụng."
            : "Đã thử chuyển sang Gemini nhưng chưa thể hoàn tất câu trả lời."}</p>
        ) : null}
        {entry.response ? <ResponseEvidence response={entry.response} /> : null}
      </div>
    </article>
  );
}
