import { BarChart3, FileText, Layers3 } from "lucide-react";

const SUGGESTED_QUESTIONS = [
  {
    label: "Phân tích bán hàng",
    question: "Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?",
    icon: BarChart3,
  },
  {
    label: "Tra cứu chính sách",
    question: "Chính sách đổi trả của cửa hàng như thế nào?",
    icon: FileText,
  },
  {
    label: "Kết hợp dữ liệu",
    question: "Top 5 sản phẩm bán chạy nhất có thuộc danh mục được miễn phí vận chuyển không?",
    icon: Layers3,
  },
] as const;

interface SuggestedQuestionsProps {
  disabled: boolean;
  onSelect: (question: string) => void;
}

export function SuggestedQuestions({ disabled, onSelect }: SuggestedQuestionsProps) {
  return (
    <section className="suggestions" aria-labelledby="suggestions-title">
      <p id="suggestions-title">Bạn có thể bắt đầu với</p>
      <div className="suggestion-grid">
        {SUGGESTED_QUESTIONS.map(({ label, question, icon: Icon }) => (
          <button
            className="suggestion-card"
            disabled={disabled}
            key={question}
            onClick={() => onSelect(question)}
            type="button"
          >
            <Icon size={19} aria-hidden="true" />
            <span>
              <strong>{label}</strong>
              <small>{question}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
