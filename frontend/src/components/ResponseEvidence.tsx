import { Check, ChevronDown, ChevronUp, Copy, Database, FileText, Table2 } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import type { ChatResponse, ResultRow, SourceReference } from "../types";

type EvidencePanel = "rows" | "sql" | "sources";

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DetailsChevron({ size = 17 }: { size?: number }) {
  return (
    <span className="details-chevron" aria-hidden="true">
      <ChevronDown className="details-chevron-down" size={size} />
      <ChevronUp className="details-chevron-up" size={size} />
    </span>
  );
}

interface EvidenceButtonProps {
  active: boolean;
  controls: string;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}

function EvidenceButton({ active, controls, icon, label, onClick }: EvidenceButtonProps) {
  return (
    <button
      aria-controls={controls}
      aria-expanded={active}
      className={`evidence-trigger ${active ? "evidence-trigger--active" : ""}`}
      onClick={onClick}
      type="button"
    >
      {icon}
      <span>{label}</span>
      <DetailsChevron size={15} />
    </button>
  );
}

function SqlPanel({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  async function copySql() {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  }

  return (
    <div className="code-wrap">
      <button aria-label="Sao chép SQL" className="copy-button" onClick={copySql} type="button">
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Đã sao chép" : "Sao chép"}
      </button>
      <pre><code>{sql}</code></pre>
    </div>
  );
}

export function ResultTable({ rows }: { rows: ResultRow[] }) {
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <div className="table-shell" aria-label="Kết quả truy vấn" role="region" tabIndex={0}>
      <table>
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => <td key={column}>{displayValue(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Sources({ sources }: { sources: SourceReference[] }) {
  return (
    <div className="sources" aria-label="Nguồn tham khảo">
      <div className="source-list">
        {sources.map((source) => (
          <details className="source-card" key={source.chunk_id}>
            <summary>
              <span><strong>{source.section_title}</strong><small>{source.source_file}</small></span>
              <DetailsChevron size={16} />
            </summary>
            <p>{source.content}</p>
          </details>
        ))}
      </div>
    </div>
  );
}

export function ResponseEvidence({ response }: { response: ChatResponse }) {
  const [activePanel, setActivePanel] = useState<EvidencePanel | null>(null);
  const evidenceId = useId();
  const showSqlEvidence = response.route === "SQL" || response.route === "HYBRID";
  const hasRows = showSqlEvidence && response.rows.length > 0;
  const hasSql = showSqlEvidence && Boolean(response.sql);
  const hasSources = (response.route === "RAG" || response.route === "HYBRID")
    && response.sources.length > 0;

  if (!hasRows && !hasSql && !hasSources) return null;

  function togglePanel(panel: EvidencePanel) {
    setActivePanel((current) => current === panel ? null : panel);
  }

  const panelIds = {
    rows: `${evidenceId}-rows`,
    sql: `${evidenceId}-sql`,
    sources: `${evidenceId}-sources`,
  };

  return (
    <div className="evidence-stack">
      <div className="evidence-toolbar" aria-label="Bằng chứng hỗ trợ" role="group">
        {hasRows ? (
          <EvidenceButton
            active={activePanel === "rows"}
            controls={panelIds.rows}
            icon={<Table2 size={15} />}
            label={`Bảng dữ liệu · ${response.rows.length}`}
            onClick={() => togglePanel("rows")}
          />
        ) : null}
        {hasSql ? (
          <EvidenceButton
            active={activePanel === "sql"}
            controls={panelIds.sql}
            icon={<Database size={15} />}
            label="Xem SQL"
            onClick={() => togglePanel("sql")}
          />
        ) : null}
        {hasSources ? (
          <EvidenceButton
            active={activePanel === "sources"}
            controls={panelIds.sources}
            icon={<FileText size={15} />}
            label={`Nguồn · ${response.sources.length}`}
            onClick={() => togglePanel("sources")}
          />
        ) : null}
      </div>

      {activePanel === "rows" && hasRows ? (
        <div className="evidence-panel" id={panelIds.rows}><ResultTable rows={response.rows} /></div>
      ) : null}
      {activePanel === "sql" && response.sql ? (
        <div className="evidence-panel" id={panelIds.sql}><SqlPanel sql={response.sql} /></div>
      ) : null}
      {activePanel === "sources" && hasSources ? (
        <div className="evidence-panel evidence-panel--sources" id={panelIds.sources}>
          <Sources sources={response.sources} />
        </div>
      ) : null}
    </div>
  );
}
