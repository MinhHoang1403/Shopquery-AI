import { Check, ChevronDown, Copy, Database, FileText } from "lucide-react";
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
        <span className="evidence-title">
          <Database size={16} aria-hidden="true" />
          Câu lệnh SQL
        </span>
        <ChevronDown className="details-chevron" size={17} aria-hidden="true" />
      </summary>
      <div className="code-wrap">
        <button className="copy-button" onClick={copySql} type="button">
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Đã sao chép" : "Sao chép"}
        </button>
        <pre><code>{sql}</code></pre>
      </div>
    </details>
  );
}

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) {
    return <p className="empty-evidence">Truy vấn không trả về bản ghi nào.</p>;
  }

  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <div className="table-shell" aria-label="Kết quả truy vấn" role="region" tabIndex={0}>
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
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
  if (sources.length === 0) {
    return <p className="empty-evidence">Không có nguồn tài liệu phù hợp.</p>;
  }

  return (
    <div className="sources" aria-label="Nguồn tham khảo">
      <h3><FileText size={16} aria-hidden="true" /> Nguồn tham khảo</h3>
      <ol>
        {sources.map((source) => (
          <li key={source.chunk_id}>
            <div>
              <strong>{source.section_title}</strong>
              <span>{source.source_file}</span>
            </div>
            <p>{source.content}</p>
          </li>
        ))}
      </ol>
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
