import { AlertCircle, Bot, UserRound } from "lucide-react";
import type { ConversationEntry, RouteLabel } from "../types";
import { ResponseEvidence } from "./ResponseEvidence";

const ROUTE_LABELS: Record<RouteLabel, string> = {
  SQL: "Dữ liệu SQL",
  RAG: "Tài liệu",
  HYBRID: "SQL + Tài liệu",
  UNSUPPORTED: "Ngoài phạm vi",
};

export function ChatMessage({ entry }: { entry: ConversationEntry }) {
  const isUser = entry.role === "user";
  const isError = entry.role === "error";

  return (
    <article className={`message message--${entry.role}`}>
      <div className="message-avatar" aria-hidden="true">
        {isUser ? <UserRound size={17} /> : isError ? <AlertCircle size={17} /> : <Bot size={17} />}
      </div>
      <div className="message-content">
        <div className="message-heading">
          <strong>{isUser ? "Bạn" : isError ? "Không thể xử lý" : "ShopQuery AI"}</strong>
          {entry.response?.route ? (
            <span className={`route-badge route-badge--${entry.response.route.toLowerCase()}`}>
              {ROUTE_LABELS[entry.response.route]}
            </span>
          ) : null}
        </div>
        <p className="message-text">{entry.text}</p>
        {entry.response ? <ResponseEvidence response={entry.response} /> : null}
      </div>
    </article>
  );
}
