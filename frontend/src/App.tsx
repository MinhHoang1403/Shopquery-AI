import { Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ChatApiError, getHealth, sendChat } from "./api";
import { ChatHeader } from "./components/ChatHeader";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { SuggestedQuestions } from "./components/SuggestedQuestions";
import type { ConversationEntry } from "./types";

let nextMessageId = 1;

function errorMessage(error: unknown): string {
  if (error instanceof ChatApiError) return error.message;
  return "Đã xảy ra lỗi không xác định. Vui lòng thử lại.";
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [health, setHealth] = useState({ checked: false, online: false });
  const conversationEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then((result) => setHealth({ checked: true, online: result.status === "ok" }))
      .catch(() => setHealth({ checked: true, online: false }));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, isLoading]);

  function updateDraft(value: string) {
    setDraft(value);
    if (validationError) setValidationError(null);
  }

  async function submitQuestion(questionOverride?: string) {
    if (isLoading) return;
    const question = (questionOverride ?? draft).trim();
    if (!question) {
      setValidationError("Vui lòng nhập câu hỏi.");
      return;
    }
    if (question.length > 2_000) {
      setValidationError("Câu hỏi không được vượt quá 2000 ký tự.");
      return;
    }

    setValidationError(null);
    setDraft("");
    setMessages((current) => [
      ...current,
      { id: nextMessageId++, role: "user", text: question },
    ]);
    setIsLoading(true);

    try {
      const response = await sendChat(question);
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId++,
          role: "assistant",
          text: response.answer,
          response,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: nextMessageId++, role: "error", text: errorMessage(error) },
      ]);
      setDraft(question);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <ChatHeader isOnline={health.online} healthChecked={health.checked} />
      <main className="chat-main">
        <div className="chat-column">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-icon" aria-hidden="true"><Sparkles size={24} /></div>
              <p className="eyebrow">HỎI DỮ LIỆU BẰNG TIẾNG VIỆT</p>
              <h1>Tìm câu trả lời từ dữ liệu cửa hàng</h1>
              <p className="welcome-copy">
                ShopQuery AI kết hợp dữ liệu bán hàng và tài liệu chính sách để trả lời rõ ràng, có căn cứ.
              </p>
              <SuggestedQuestions disabled={isLoading} onSelect={submitQuestion} />
            </div>
          ) : (
            <section className="conversation" aria-label="Cuộc trò chuyện" aria-live="polite">
              {messages.map((entry) => <ChatMessage entry={entry} key={entry.id} />)}
              {isLoading ? (
                <div className="message message--assistant loading-message" role="status">
                  <div className="message-avatar" aria-hidden="true"><Sparkles size={17} /></div>
                  <div className="typing-dots" aria-label="ShopQuery AI đang xử lý">
                    <span /><span /><span />
                  </div>
                </div>
              ) : null}
              <div ref={conversationEnd} />
            </section>
          )}
        </div>
      </main>
      <footer className="composer-area">
        <div className="chat-column">
          <ChatInput
            disabled={isLoading}
            onChange={updateDraft}
            onSubmit={() => submitQuestion()}
            validationError={validationError}
            value={draft}
          />
          <p className="disclaimer">AI có thể mắc lỗi. Hãy kiểm tra dữ liệu quan trọng trước khi sử dụng.</p>
        </div>
      </footer>
    </div>
  );
}
