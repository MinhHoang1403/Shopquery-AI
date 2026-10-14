import { Check, ChevronDown, ChevronUp, Copy, Database, FileText, Table2 } from "lucide-react";
import { useState } from "react";
import type { ChatResponse, SourceReference } from "../types";

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

function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  async function copySql() {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  }

  return (
    <details className="evidence-card sql-card">
      <summary>
        <span className="evidence-title"><Database size={15} /> Xem SQL</span>
        <DetailsChevron />
      </summary>
      <div className="code-wrap">
        <button aria-label="Sao chép SQL" className="copy-button" onClick={copySql} type="button">
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Đã sao chép" : "Sao chép"}
        </button>
        <pre><code>{sql}</code></pre>
      </div>
    </details>
  );
}

export function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
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

function ResultBlock({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return null;
  return (
    <details className="evidence-card result-card">
      <summary>
        <span className="evidence-title"><Table2 size={15} /> Xem bảng dữ liệu · {rows.length} dòng</span>
        <DetailsChevron />
      </summary>
      <div className="result-section"><ResultTable rows={rows} /></div>
    </details>
  );
}

function Sources({ sources }: { sources: SourceReference[] }) {
  if (sources.length === 0) return <p className="empty-evidence">Không có nguồn tài liệu phù hợp.</p>;
  return (
    <div className="sources" aria-label="Nguồn tham khảo">
      <div className="evidence-label"><FileText size={15} /> Nguồn tham khảo · {sources.length}</div>
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
  const showSql = response.route === "SQL" || response.route === "HYBRID";
  const showSources = response.route === "RAG" || response.route === "HYBRID";
  return (
    <div className="evidence-stack">
      {showSql ? <ResultBlock rows={response.rows} /> : null}
      {showSql && response.sql ? <SqlBlock sql={response.sql} /> : null}
      {showSources ? <Sources sources={response.sources} /> : null}
    </div>
  );
}
