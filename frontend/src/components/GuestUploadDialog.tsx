import { useEffect, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import type { GuestClient, GuestPreview, GuestStatus } from "../guest";
import { guestDataset } from "../guest";
import type { Dataset } from "../types";
import { Modal } from "./Dialogs";
import { ResultTable } from "./ResponseEvidence";
import { RelationshipPanel } from "./RelationshipPanel";

export function GuestUploadDialog({ client, status, onClose, onImported }: {
  client: GuestClient; status: GuestStatus | null; onClose: () => void; onImported: (dataset: Dataset) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<GuestPreview | null>(null);
  const [sheet, setSheet] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function inspect(selected: File, selectedSheet?: string | null) {
    controller.current?.abort();
    const pending = new AbortController(); controller.current = pending;
    setBusy(true); setError(null); setPreview(null);
    try {
      const value = await client.previewFile(selected, selectedSheet, pending.signal);
      if (pending.signal.aborted) return;
      setPreview(value.preview); setSheet(value.preview.sheet_name);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Không thể kiểm tra tệp.");
    } finally { if (controller.current === pending) setBusy(false); }
  }

  async function upload() {
    if (!file || !preview) return;
    setBusy(true); setError(null);
    try {
      const value = await client.importFile(file, sheet);
      const dataset = guestDataset(value.status);
      if (dataset) onImported(dataset);
      setFile(null); setPreview(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể thêm tệp."); }
    finally { setBusy(false); }
  }

  return <Modal className="guest-upload-modal" title="Tệp tạm của phiên khách" description="Tệp chỉ dùng trong phiên này, không lưu vào tài khoản. Refresh sẽ làm mới không gian dùng thử." onClose={() => { if (!busy) onClose(); }}>
    <div className="upload-flow">
      <p className="guest-limits">{status ? `${status.files.length}/${status.max_files} tệp · ${status.max_file_bytes / 1048576} MB/tệp · ${status.max_rows.toLocaleString("vi")} dòng · ${status.max_columns} cột` : "Đang đọc giới hạn từ máy chủ…"}</p>
      {status?.files.length ? <ul className="guest-file-list">{status.files.map((item) => <li key={item.file_id}>{item.filename} · {item.kind === "table" ? `${item.row_count} dòng` : `${item.chunk_count} đoạn tài liệu`}</li>)}</ul> : null}
      {status && status.files.length >= status.max_files ? <p role="status">Đã đạt giới hạn tệp của phiên. Đăng nhập để quản lý bộ dữ liệu lâu dài.</p> : null}
      <label className="file-drop compact-drop" htmlFor="guest-file"><UploadCloud size={22} /><span><strong>Thêm CSV, XLSX, PDF, DOCX, TXT hoặc MD</strong><small>PDF cần text layer; không OCR. Chỉ xem trước, chưa gọi AI.</small></span>
        <input id="guest-file" type="file" accept=".csv,.xlsx,.pdf,.docx,.txt,.md" disabled={busy || !status || status.files.length >= status.max_files} onChange={(event) => {
          const value = event.target.files?.[0]; event.target.value = "";
          if (value) { setFile(value); setSheet(null); void inspect(value); }
        }} />
      </label>
      {busy ? <p role="status">Đang xử lý tệp tạm…</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {preview ? <div className="preview-panel">
        <strong>{preview.filename}</strong>
        {preview.sheet_names.length > 1 ? <label className="field-label" htmlFor="guest-sheet">Sheet<select id="guest-sheet" value={sheet ?? ""} disabled={busy} onChange={(event) => { if (file) void inspect(file, event.target.value); }}>{preview.sheet_names.map((name) => <option key={name}>{name}</option>)}</select></label> : null}
        {preview.kind === "table" ? <ResultTable rows={preview.rows} /> : <p>{preview.chunk_count} đoạn tài liệu đã parse. Embedding chỉ chạy khi hỏi và AI được cho phép.</p>}
        {preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        <button className="primary-button" disabled={busy} onClick={() => void upload()} type="button">Dùng tệp trong phiên này</button>
      </div> : null}
      <details className="guest-privacy"><summary>Quyền riêng tư và thời gian lưu</summary><p>Không tải thông tin cá nhân, mật khẩu hoặc dữ liệu chưa được phép chia sẻ. {status ? `Máy chủ dọn tệp sau tối đa ${Math.ceil(status.ttl_seconds / 60)} phút kể từ khi tạo phiên.` : "Tệp được dọn khi hết hạn phiên."} Nếu bật AI, dữ liệu liên quan có thể gửi tới Knowledge/Gemini; RAG dùng Google Embedding. Xem trước không gọi AI.</p></details>
      {status?.sql_join_v1_enabled ? <RelationshipPanel
        key={JSON.stringify(status.files.map((file) => [file.file_id, file.columns]))}
        client={client.relationships} disabled={busy}
        tables={status.files.filter((file) => file.kind === "table").map((file) => ({ id: file.file_id, name: file.filename, columns: file.columns }))}
      /> : null}
      <div className="dialog-actions"><button className="secondary-button" disabled={busy} type="button" onClick={onClose}>Đóng</button></div>
    </div>
  </Modal>;
}
