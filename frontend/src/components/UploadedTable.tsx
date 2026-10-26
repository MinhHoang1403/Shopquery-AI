import { ChevronDown, FileSpreadsheet, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { getDatasetTablePreview } from "../api";
import type { DatasetTable, DatasetTablePreview } from "../types";
import { ResultTable } from "./ResponseEvidence";

export function UploadedTable({ datasetId, table, deletionDisabled, onDelete }: {
  datasetId: number; table: DatasetTable; deletionDisabled?: boolean; onDelete: () => void;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<DatasetTablePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function toggle() {
    if (open) {
      request.current?.abort(); setLoading(false); setOpen(false); return;
    }
    setOpen(true);
    if (preview || table.dataset_table_id == null) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError("");
    try {
      const value = await getDatasetTablePreview(datasetId, table.dataset_table_id, controller.signal);
      if (!controller.signal.aborted) setPreview(value);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Không đọc được dữ liệu.");
    } finally {
      if (request.current === controller && !controller.signal.aborted) setLoading(false);
    }
  }
  return <div className="uploaded-table">
    <div className="source-row">
      <button className="table-preview-toggle" type="button" disabled={table.dataset_table_id == null}
        aria-label={`Xem dữ liệu ${table.display_name}`} aria-expanded={open} aria-controls={panelId} onClick={() => void toggle()}>
        <FileSpreadsheet size={17} aria-hidden="true" />
        <span><strong>{table.display_name}</strong><small>{table.original_filename} · {table.row_count.toLocaleString("vi-VN")} dòng · {table.column_count} cột</small></span>
        <ChevronDown className={open ? "chevron-expanded" : ""} size={17} aria-hidden="true" />
      </button>
      <button aria-label={`Xóa bảng ${table.display_name}`} disabled={deletionDisabled || table.dataset_table_id == null} onClick={onDelete} type="button"><Trash2 size={16} /></button>
    </div>
    {open ? <section id={panelId} className="uploaded-table-preview" aria-label={`Dữ liệu ${table.display_name}`}>
      {loading ? <p role="status">Đang đọc dữ liệu…</p> : error ? <p role="alert" className="form-error">{error}</p> : preview ? <>
        <p className="empty-source">Dữ liệu đã nhập · Hiển thị {preview.rows.length} / {preview.row_count.toLocaleString("vi-VN")} dòng</p>
        <ResultTable rows={preview.rows} columns={preview.columns.map((column) => column.source_name)} formatNumbers={false} />
        {!preview.rows.length ? <p>Chưa có dòng dữ liệu.</p> : null}
      </> : null}
    </section> : null}
  </div>;
}
