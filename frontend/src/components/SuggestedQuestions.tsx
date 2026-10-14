import { ArrowUpRight } from "lucide-react";

interface SuggestedQuestion {
  label: string;
  question: string;
  kind: "analysis" | "document" | "hybrid";
}

interface SuggestedQuestionsProps {
  disabled: boolean;
  questions: SuggestedQuestion[];
  onSelect: (question: string) => void;
}

export function SuggestedQuestions({ disabled, questions, onSelect }: SuggestedQuestionsProps) {
  return (
    <section className="suggestions" aria-label="Gợi ý câu hỏi">
      <div className="suggestion-grid">
        {questions.map(({ label, question }) => (
          <button
            aria-label={`${label}: ${question}`}
            className="suggestion-chip"
            disabled={disabled}
            key={question}
            onClick={() => onSelect(question)}
            title={question}
            type="button"
          >
            <span>{label}</span>
            <ArrowUpRight aria-hidden="true" size={14} />
          </button>
        ))}
      </div>
    </section>
  );
}
