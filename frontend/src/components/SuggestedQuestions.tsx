import { ArrowUpRight, BarChart3, FileText, Layers3 } from "lucide-react";

interface SuggestedQuestion {
  label: string;
  question: string;
  kind: "analysis" | "document" | "hybrid";
}

const ICONS = {
  analysis: BarChart3,
  document: FileText,
  hybrid: Layers3,
};

interface SuggestedQuestionsProps {
  disabled: boolean;
  questions: SuggestedQuestion[];
  onSelect: (question: string) => void;
}

export function SuggestedQuestions({ disabled, questions, onSelect }: SuggestedQuestionsProps) {
  return (
    <section className="suggestions" aria-labelledby="suggestions-title">
      <p id="suggestions-title">Gợi ý để bắt đầu</p>
      <div className="suggestion-grid">
        {questions.map(({ label, question, kind }) => {
          const Icon = ICONS[kind];
          return (
            <button className="suggestion-card" disabled={disabled} key={question} onClick={() => onSelect(question)} type="button">
              <span className="suggestion-icon"><Icon size={18} /></span>
              <span><strong>{label}</strong><small>{question}</small></span>
              <ArrowUpRight className="suggestion-arrow" size={16} />
            </button>
          );
        })}
      </div>
    </section>
  );
}
