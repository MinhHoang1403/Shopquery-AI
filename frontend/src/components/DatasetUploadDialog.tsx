import { AlertCircle, FileSpreadsheet, FileText, Plus, Trash2, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  createDataset,
  deleteDatasetDocument,
  getDatasetDocuments,
  importDataset,
  importDatasetTable,
  previewDataset,
  uploadDatasetDocument,
} from "../api";
import type { Dataset, DatasetDocument, DatasetPreview } from "../types";
import { Modal } from "./Dialogs";
import { ResultTable } from "./ResponseEvidence";

interface DatasetUploadDialogProps {
  datasets: Dataset[];
  onClose: () => void;
  onImported: (dataset: Dataset) => void;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Không thể xử lý dữ liệu.";
}

export function DatasetUploadDialog({ datasets, onClose, onImported }: DatasetUploadDialogProps) {
  const uploaded = datasets.filter(
    (item): item is Dataset & { dataset_id: number } => item.kind === "uploaded" && item.dataset_id !== null,
  );
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [workspace, setWorkspace] = useState<Dataset | null>(null);
  const [workspaceName, setWorkspaceName] = useState("");
  const [documents, setDocuments] = useState<DatasetDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [tableName, setTableName] = useState("");
  const [selectedSheet, setSelectedSheet] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const previewController = useRef<AbortController | null>(null);

  useEffect(() => () => previewController.current?.abort(), []);

  async function selectWorkspace(dataset: Dataset | null) {
    setWorkspace(dataset);
    setFile(null);
    setPreview(null);
    setError(null);
    if (!dataset?.dataset_id) {
      setDocuments([]);
      return;
    }
    try {
      setDocuments(await getDatasetDocuments(dataset.dataset_id));
    } catch (loadError) {
      setError(messageFromError(loadError));
    }
  }

  async function createWorkspace() {
    if (!workspaceName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createDataset(workspaceName.trim());
      setWorkspace(created);
      onImported(created);
    } catch (createError) {
      setError(messageFromError(createError));
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview(selectedFile: File, sheetName?: string | null) {
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setIsPreviewing(true);
    setError(null);
    try {
      const result = await previewDataset(selectedFile, sheetName, controller.signal);
      setPreview(result);
      setSelectedSheet(result.sheet_name);
    } catch (previewError) {
      if (previewError instanceof DOMException && previewError.name === "AbortError") return;
      setPreview(null);
      setError(messageFromError(previewError));
    } finally {
      if (previewController.current === controller) setIsPreviewing(false);
    }
  }

  function chooseTableFile(selectedFile: File | null) {
    setFile(selectedFile);
    setPreview(null);
    setSelectedSheet(null);
    setError(null);
    if (!selectedFile) return;
    setTableName(selectedFile.name.replace(/\.(csv|xlsx)$/i, "").slice(0, 120));
    if (!workspaceName.trim()) {
      setWorkspaceName(selectedFile.name.replace(/\.(csv|xlsx)$/i, "").slice(0, 120));
    }
    void loadPreview(selectedFile);
  }

  async function quickImport() {
    if (!file || !preview || !workspaceName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await importDataset(file, workspaceName.trim(), selectedSheet);
      setWorkspace(created);
      onImported(created);
    } catch (importError) {
      setError(messageFromError(importError));
    } finally {
      setBusy(false);
    }
  }

  async function addTable() {
    if (!workspace?.dataset_id || !file || !preview || !tableName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await importDatasetTable(
        workspace.dataset_id,
        file,
        tableName.trim(),
        selectedSheet,
      );
      setWorkspace(updated);
      setFile(null);
      setPreview(null);
      onImported(updated);
    } catch (importError) {
      setError(messageFromError(importError));
    } finally {
      setBusy(false);
    }
  }

  async function addDocument(selectedFile: File | null) {
    if (!workspace?.dataset_id || !selectedFile) return;
    setBusy(true);
    setError(null);
    try {
      const created = await uploadDatasetDocument(workspace.dataset_id, selectedFile);
      setDocuments((current) => [created, ...current]);
      const updated = { ...workspace, document_count: (workspace.document_count ?? 0) + 1 };
      setWorkspace(updated);
      onImported(updated);
    } catch (uploadError) {
      setError(messageFromError(uploadError));
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument(document: DatasetDocument) {
    if (!workspace?.dataset_id) return;
    if (!window.confirm(`Xóa tài liệu “${document.original_filename}” và toàn bộ chunks?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteDatasetDocument(workspace.dataset_id, document.document_id);
      setDocuments((current) => current.filter((item) => item.document_id !== document.document_id));
      const updated = { ...workspace, document_count: Math.max(0, (workspace.document_count ?? 1) - 1) };
      setWorkspace(updated);
      onImported(updated);
    } catch (deleteError) {
      setError(messageFromError(deleteError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Quản lý bộ dữ liệu"
      description="Tạo workspace và quản lý các bảng, tài liệu dùng cho SQL, RAG và Hybrid."
      onClose={onClose}
    >
      <div className="upload-flow workspace-flow">
        <div className="workspace-mode" role="tablist" aria-label="Cách quản lý dữ liệu">
          <button aria-selected={mode === "new"} className={mode === "new" ? "secondary-button is-active" : "secondary-button"} onClick={() => { setMode("new"); void selectWorkspace(null); }} role="tab" type="button">
            <Plus size={16} /> Tạo bộ dữ liệu mới
          </button>
          <button aria-selected={mode === "existing"} className={mode === "existing" ? "secondary-button is-active" : "secondary-button"} onClick={() => { setMode("existing"); void selectWorkspace(uploaded[0] ?? null); }} role="tab" type="button">
            Thêm vào bộ hiện có
          </button>
        </div>

        {mode === "new" && !workspace ? (
          <>
            <div className="workspace-create">
              <label className="field-label" htmlFor="workspace-name">Tên bộ dữ liệu
                <input id="workspace-name" maxLength={120} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="Ví dụ: Kinh doanh Q3/2026" value={workspaceName} />
              </label>
              <button className="primary-button" disabled={busy || !workspaceName.trim()} onClick={createWorkspace} type="button">{busy ? "Đang tạo…" : "Tạo workspace rỗng"}</button>
            </div>
            <label className="file-drop compact-drop" htmlFor="quick-dataset-file">
              <UploadCloud size={21} /><span><strong>Hoặc import nhanh CSV/XLSX thành bộ mới</strong><small>Giữ tương thích với luồng import cũ</small></span>
              <input accept=".csv,.xlsx" id="quick-dataset-file" onChange={(event) => chooseTableFile(event.target.files?.[0] ?? null)} type="file" />
            </label>
            {isPreviewing ? <div className="upload-status" role="status">Đang kiểm tra file…</div> : null}
            {preview ? (
              <div className="preview-panel">
                <div className="preview-stats"><span><strong>{preview.row_count.toLocaleString("vi-VN")}</strong> dòng</span><span><strong>{preview.column_count}</strong> cột</span></div>
                {preview.sheet_names.length > 1 ? (
                  <label className="field-label" htmlFor="quick-sheet-select">Sheet
                    <select id="quick-sheet-select" onChange={(event) => { setSelectedSheet(event.target.value); if (file) void loadPreview(file, event.target.value); }} value={selectedSheet ?? ""}>{preview.sheet_names.map((name) => <option key={name} value={name}>{name}</option>)}</select>
                  </label>
                ) : null}
                <ResultTable rows={preview.rows} />
                <button className="primary-button" disabled={busy || !workspaceName.trim()} onClick={quickImport} type="button">{busy ? "Đang import…" : "Import thành bộ mới"}</button>
              </div>
            ) : null}
          </>
        ) : null}

        {mode === "existing" ? (
          <label className="field-label" htmlFor="workspace-select">Bộ dữ liệu
            <select id="workspace-select" onChange={(event) => { const id = Number(event.target.value); void selectWorkspace(uploaded.find((item) => item.dataset_id === id) ?? null); }} value={workspace?.dataset_id ?? ""}>
              {uploaded.length === 0 ? <option value="">Chưa có bộ dữ liệu</option> : null}
              {uploaded.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.name}</option>)}
            </select>
          </label>
        ) : null}

        {error ? <p className="form-error upload-error" role="alert"><AlertCircle size={16} /> {error}</p> : null}

        {workspace?.dataset_id ? (
          <>
            <div className="workspace-summary"><strong>{workspace.name}</strong><span>{workspace.table_count ?? workspace.tables?.length ?? 0} bảng · {workspace.document_count ?? 0} tài liệu</span></div>
            <section className="workspace-section">
              <h3>Bảng dữ liệu</h3>
              <div className="source-list">
                {(workspace.tables ?? []).map((table) => (
                  <div className="source-row" key={table.dataset_table_id ?? table.display_name}>
                    <FileSpreadsheet size={17} /><span><strong>{table.display_name}</strong><small>{table.original_filename} · {table.row_count.toLocaleString("vi-VN")} dòng</small></span>
                  </div>
                ))}
                {(workspace.tables ?? []).length === 0 ? <p className="empty-source">Chưa có bảng dữ liệu.</p> : null}
              </div>
              <label className="file-drop compact-drop" htmlFor="dataset-file">
                <UploadCloud size={21} /><span><strong>Thêm CSV hoặc XLSX</strong><small>Tối đa 10 MB · 5.000 dòng · 30 cột</small></span>
                <input accept=".csv,.xlsx" id="dataset-file" onChange={(event) => chooseTableFile(event.target.files?.[0] ?? null)} type="file" />
              </label>
              {isPreviewing ? <div className="upload-status" role="status">Đang kiểm tra file…</div> : null}
              {preview ? (
                <div className="preview-panel">
                  <div className="preview-stats"><span><strong>{preview.row_count.toLocaleString("vi-VN")}</strong> dòng</span><span><strong>{preview.column_count}</strong> cột</span></div>
                  {preview.sheet_names.length > 1 ? (
                    <label className="field-label" htmlFor="sheet-select">Sheet
                      <select id="sheet-select" onChange={(event) => { setSelectedSheet(event.target.value); if (file) void loadPreview(file, event.target.value); }} value={selectedSheet ?? ""}>{preview.sheet_names.map((name) => <option key={name} value={name}>{name}</option>)}</select>
                    </label>
                  ) : null}
                  <ResultTable rows={preview.rows} />
                  <label className="field-label" htmlFor="table-name">Tên hiển thị của bảng<input id="table-name" maxLength={120} onChange={(event) => setTableName(event.target.value)} value={tableName} /></label>
                  <button className="primary-button" disabled={busy || !tableName.trim()} onClick={addTable} type="button">{busy ? "Đang import…" : "Thêm bảng"}</button>
                </div>
              ) : null}
            </section>
            <section className="workspace-section">
              <h3>Tài liệu</h3>
              <div className="source-list">
                {documents.map((document) => (
                  <div className="source-row" key={document.document_id}>
                    <FileText size={17} /><span><strong>{document.original_filename}</strong><small>{document.file_type.toUpperCase()} · {document.chunk_count} chunks</small></span>
                    <button aria-label={`Xóa ${document.original_filename}`} disabled={busy} onClick={() => void removeDocument(document)} type="button"><Trash2 size={16} /></button>
                  </div>
                ))}
                {documents.length === 0 ? <p className="empty-source">Chưa có tài liệu.</p> : null}
              </div>
              <label className="file-drop compact-drop" htmlFor="document-file">
                <FileText size={21} /><span><strong>Thêm PDF, DOCX, TXT hoặc MD</strong><small>PDF cần có text layer; không hỗ trợ OCR</small></span>
                <input accept=".pdf,.docx,.txt,.md" disabled={busy} id="document-file" onChange={(event) => void addDocument(event.target.files?.[0] ?? null)} type="file" />
              </label>
            </section>
          </>
        ) : null}

        <div className="dialog-actions"><button className="secondary-button" disabled={busy} onClick={onClose} type="button">Đóng</button></div>
      </div>
    </Modal>
  );
}
