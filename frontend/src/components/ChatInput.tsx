import { ArrowUp } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import type { ModelId, ModelOption, RouteLabel } from "../types";
import { ModelSelector } from "./ModelSelector";

interface ChatInputProps {
  value: string;
  disabled: boolean;
  validationError: string | null;
  datasetName: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  models: ModelOption[];
  selectedModel: ModelId;
  onModelSelect: (model: ModelId) => void;
  placeholder?: string;
  submitUnavailableReason?: string | null;
  routeChoice?: Exclude<RouteLabel, "UNSUPPORTED"> | "";
  onRouteChange?: (route: Exclude<RouteLabel, "UNSUPPORTED"> | "") => void;
  hasTables?: boolean;
  hasDocuments?: boolean;
}

export function ChatInput({
  value,
  disabled,
  validationError,
  datasetName,
  onChange,
  onSubmit,
  models,
  selectedModel,
  onModelSelect,
  placeholder,
  submitUnavailableReason,
  routeChoice = "",
  onRouteChange,
  hasTables,
  hasDocuments,
}: ChatInputProps) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const showCharacterCount = value.length > 0;
  const describedBy = [validationError ? "composer-error" : null, showCharacterCount ? "composer-help" : null]
    .filter(Boolean)
    .join(" ") || undefined;

  useEffect(() => {
    const input = textarea.current;
    if (!input) return;
    function resize() {
      if (!input) return;
      input.style.height = "0px";
      input.style.height = value ? `${Math.min(input.scrollHeight, 160)}px` : "";
    }
    resize();
    if (typeof ResizeObserver === "undefined") return;
    let previousWidth = input.clientWidth;
    const observer = new ResizeObserver(() => {
      if (input.clientWidth !== previousWidth) {
        previousWidth = input.clientWidth;
        resize();
      }
    });
    observer.observe(input);
    return () => observer.disconnect();
  }, [value]);

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
          ref={textarea}
          id="chat-message"
          aria-describedby={describedBy}
          aria-invalid={Boolean(validationError)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? `Hỏi về ${datasetName.toLocaleLowerCase("vi")}…`}
          rows={1}
          value={value}
        />
        <div className="composer-controls">
          <ModelSelector models={models} selectedModel={selectedModel} disabled={disabled} onSelect={onModelSelect} />
          {onRouteChange ? (
            <select className="source-selector" aria-label="Nguồn trả lời" disabled={disabled} value={routeChoice}
              onChange={(event) => onRouteChange(event.target.value as Exclude<RouteLabel, "UNSUPPORTED"> | "")}>
              <option value="">Tự chọn nguồn</option>
              <option value="SQL" disabled={!hasTables}>Bảng dữ liệu</option>
              <option value="RAG" disabled={!hasDocuments}>Tài liệu</option>
              <option value="HYBRID" disabled={!hasTables || !hasDocuments}>Bảng + Tài liệu</option>
            </select>
          ) : null}
          <button
            aria-label="Gửi câu hỏi"
            className="send-button"
            disabled={disabled || value.trim().length === 0}
            aria-disabled={Boolean(disabled || !value.trim() || submitUnavailableReason)}
            title={submitUnavailableReason ?? "Gửi câu hỏi"}
            type="submit"
          >
            <ArrowUp size={19} strokeWidth={2.4} aria-hidden="true" />
          </button>
        </div>
      </div>
      {validationError || showCharacterCount ? (
        <div className="composer-meta">
          {validationError ? <span id="composer-error" className="validation-message" role="alert">{validationError}</span> : null}
          {showCharacterCount ? (
            <span
              id="composer-help"
              className={value.length > 2_000 ? "character-count character-count--over" : "character-count"}
            >
              {value.length}/2000
            </span>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
