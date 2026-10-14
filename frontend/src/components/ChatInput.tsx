import { SendHorizontal } from "lucide-react";
import type { FormEvent, KeyboardEvent } from "react";

interface ChatInputProps {
  value: string;
  disabled: boolean;
  validationError: string | null;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function ChatInput({
  value,
  disabled,
  validationError,
  onChange,
  onSubmit,
}: ChatInputProps) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <div className={`composer-box ${validationError ? "composer-box--invalid" : ""}`}>
        <label className="sr-only" htmlFor="chat-message">
          Nhập câu hỏi cho ShopQuery AI
        </label>
        <textarea
          id="chat-message"
          aria-describedby="composer-help composer-error"
          aria-invalid={Boolean(validationError)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Hỏi về doanh số, sản phẩm hoặc chính sách cửa hàng…"
          rows={1}
          value={value}
        />
        <button
          aria-label="Gửi câu hỏi"
          className="send-button"
          disabled={disabled || value.trim().length === 0}
          type="submit"
        >
          <SendHorizontal size={19} aria-hidden="true" />
        </button>
      </div>
      <div className="composer-meta">
        <span id="composer-error" className="validation-message" role="alert">
          {validationError ?? ""}
        </span>
        <span id="composer-help" className={value.length > 2_000 ? "character-count character-count--over" : "character-count"}>
          {value.length}/2000
        </span>
      </div>
    </form>
  );
}
