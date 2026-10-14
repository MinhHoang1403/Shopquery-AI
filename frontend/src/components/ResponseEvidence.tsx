import { Check, ChevronDown, Copy, Database, FileText, Table2 } from "lucide-react";
import { useState } from "react";
import type { ChatResponse, SourceReference } from "../types";

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
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
        <span className="evidence-title"><Database size={15} /> Xem câu lệnh SQL</span>
        <ChevronDown className="details-chevron" size={17} />
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
  if (rows.length === 0) return <p className="empty-evidence">Không có bản ghi phù hợp.</p>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <div className="result-section">
      <div className="evidence-label"><Table2 size={15} /> Kết quả · {rows.length} dòng</div>
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
    </div>
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
              <ChevronDown className="details-chevron" size={16} />
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
      {showSql && response.sql ? <SqlBlock sql={response.sql} /> : null}
      {showSql ? <ResultTable rows={response.rows} /> : null}
      {showSources ? <Sources sources={response.sources} /> : null}
    </div>
  );
}
