import { AlertCircle, FileText, Plus, Trash2, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createDataset,
  createRelationshipClient,
  deleteDataset,
  deleteDatasetDocument,
  deleteDatasetTable,
  getDataset,
  getDatasetDocuments,
  getUploadLimits,
  type UploadLimits,
  importDataset,
  importDatasetTable,
  previewDataset,
  uploadDatasetDocument,
} from "../api";
import type { Dataset, DatasetDocument, DatasetPreview, DatasetTable } from "../types";
import { Modal } from "./Dialogs";
import { ResultTable } from "./ResponseEvidence";
import { RelationshipPanel } from "./RelationshipPanel";
import { UploadedTable } from "./UploadedTable";

interface DatasetUploadDialogProps {
  datasets: Dataset[];
  onClose: () => void;
  onImported: (dataset: Dataset) => void;
  onDeleted: (dataset: Dataset) => void;
  deletionDisabled?: boolean;
  initialDatasetId?: number | null;
}

type DeleteTarget =
  | { kind: "dataset"; name: string }
  | { kind: "table"; name: string; id: number }
  | { kind: "document"; name: string; id: number };

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Không thể xử lý dữ liệu.";
}

export function DatasetUploadDialog({ datasets, onClose, onImported, onDeleted, deletionDisabled, initialDatasetId }: DatasetUploadDialogProps) {
  const uploaded = datasets.filter(
    (item): item is Dataset & { dataset_id: number } => item.kind === "uploaded" && item.dataset_id !== null,
  );
  const [mode, setMode] = useState<"new" | "existing">(initialDatasetId ? "existing" : "new");
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
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteHistory, setDeleteHistory] = useState(false);
  const previewController = useRef<AbortController | null>(null);
  const workspaceController = useRef<AbortController | null>(null);
  const confirmation = useRef<HTMLElement | null>(null);
  const [limits, setLimits] = useState<UploadLimits | null>(null);
  const [limitsError, setLimitsError] = useState<string | null>(null);
  const relationshipDatasetId = workspace?.dataset_id;
  const relationshipEnabled = limits?.sql_join_v1_enabled === true;
  const relationshipClient = useMemo(() => relationshipEnabled && relationshipDatasetId ? createRelationshipClient(relationshipDatasetId) : null, [relationshipDatasetId, relationshipEnabled]);

  useEffect(() => {
    const controller = new AbortController();
    getUploadLimits(controller.signal).then(setLimits).catch((reason: unknown) => {
      if (!controller.signal.aborted) setLimitsError(messageFromError(reason));
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (initialDatasetId) void selectWorkspace(datasets.find((item) => item.dataset_id === initialDatasetId) ?? null);
    return () => { previewController.current?.abort(); workspaceController.current?.abort(); };
    // This dialog opens at the selected workspace; later selection is explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!deleteTarget) return;
    confirmation.current?.focus();
    confirmation.current?.scrollIntoView({ block: "nearest" });
  }, [deleteTarget]);

  async function selectWorkspace(dataset: Dataset | null) {
    workspaceController.current?.abort();
    const controller = new AbortController();
    workspaceController.current = controller;
    setBusy(false);
    previewController.current?.abort();
    setIsPreviewing(false);
    setWorkspace(dataset);
    setFile(null);
    setPreview(null);
    setError(null);
    setDeleteTarget(null);
    setDeleteHistory(false);
    setDocuments([]);
    if (!dataset?.dataset_id) {
      setDocuments([]);
      return;
    }
    setBusy(true);
    try {
      const [detail, items] = await Promise.all([
        getDataset(dataset.dataset_id, controller.signal), getDatasetDocuments(dataset.dataset_id, controller.signal),
      ]);
      if (controller.signal.aborted) return;
      setWorkspace(detail);
      setDocuments(items);
    } catch (loadError) {
      if (controller.signal.aborted) return;
      setError(messageFromError(loadError));
      setWorkspace(null);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
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
      const result = await previewDataset(
        selectedFile,
        sheetName,
        controller.signal,
        workspace?.dataset_id,
      );
      if (controller.signal.aborted) return;
      setPreview(result);
      setSelectedSheet(result.sheet_name);
    } catch (previewError) {
      if (controller.signal.aborted) return;
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
      setFile(null); setPreview(null);
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

  function requestTableDelete(table: DatasetTable) {
    if (table.dataset_table_id === null || table.dataset_table_id === undefined) return;
    setError(null);
    setDeleteTarget({ kind: "table", id: table.dataset_table_id, name: table.display_name });
  }

  async function confirmSourceDelete() {
    if (!workspace?.dataset_id || !deleteTarget || deletionDisabled || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (deleteTarget.kind === "dataset") {
        await deleteDataset(workspace.dataset_id, deleteHistory);
        onDeleted(workspace);
        setWorkspace(null);
        setDocuments([]);
        setFile(null);
        setPreview(null);
      } else {
        if (deleteTarget.kind === "table") {
          await deleteDatasetTable(workspace.dataset_id, deleteTarget.id);
        } else {
          await deleteDatasetDocument(workspace.dataset_id, deleteTarget.id);
        }
        const tables = (workspace.tables ?? []).filter((item) =>
          deleteTarget.kind !== "table" || item.dataset_table_id !== deleteTarget.id,
        );
        const first = tables[0];
        const updated = deleteTarget.kind === "table" ? {
          ...workspace, tables, table_count: tables.length,
          original_filename: first?.original_filename ?? null,
          file_type: first?.file_type ?? null, sheet_name: first?.sheet_name ?? null,
          columns: first?.columns ?? [], row_count: first?.row_count ?? null,
          column_count: first?.column_count ?? null,
        } : { ...workspace, document_count: Math.max(0, (workspace.document_count ?? 1) - 1) };
        setWorkspace(updated);
        setDocuments((current) => current.filter((item) =>
          deleteTarget.kind !== "document" || item.document_id !== deleteTarget.id,
        ));
        onImported(updated);
      }
      setDeleteTarget(null);
      setDeleteHistory(false);
    } catch (deleteError) {
      setError(messageFromError(deleteError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Quản lý bộ dữ liệu"
      description="Thêm bảng hoặc tài liệu. Hệ thống tự chuẩn bị dữ liệu để bạn trò chuyện."
      onClose={() => { if (!busy) onClose(); }}
    >
      <div className="upload-flow workspace-flow">
        <fieldset className="workspace-controls" disabled={busy || deleteTarget !== null}>
        <div className="workspace-mode" role="tablist" aria-label="Cách quản lý dữ liệu">
          <button aria-selected={mode === "new"} className={mode === "new" ? "secondary-button is-active" : "secondary-button"} onClick={() => { setMode("new"); void selectWorkspace(null); }} role="tab" type="button">
            <Plus size={16} /> Tạo bộ dữ liệu mới
          </button>
          <button aria-selected={mode === "existing"} className={mode === "existing" ? "secondary-button is-active" : "secondary-button"} onClick={() => { setMode("existing"); void selectWorkspace(uploaded[0] ?? null); }} role="tab" type="button">
            Quản lý bộ hiện có
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
              <UploadCloud size={21} /><span><strong>Tải CSV hoặc XLSX</strong><small>Tên bộ dữ liệu được lấy từ tên tệp, bạn có thể đổi nếu muốn.</small></span>
              <input accept=".csv,.xlsx" aria-label="Tải CSV hoặc XLSX" id="quick-dataset-file" onChange={(event) => { chooseTableFile(event.target.files?.[0] ?? null); event.target.value = ""; }} type="file" />
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
              <option value="">{uploaded.length === 0 ? "Chưa có bộ dữ liệu" : "Chọn bộ dữ liệu cần quản lý"}</option>
              {uploaded.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.name}</option>)}
            </select>
          </label>
        ) : null}

        {error && !deleteTarget ? <p className="form-error upload-error" role="alert"><AlertCircle size={16} /> {error}</p> : null}

        {workspace?.dataset_id ? (
          <>
            <div className="workspace-summary"><strong>{workspace.name}</strong><span>{workspace.table_count ?? workspace.tables?.length ?? 0} bảng · {workspace.document_count ?? 0} tài liệu</span><button className="danger-button" disabled={deletionDisabled} onClick={() => { setError(null); setDeleteHistory(false); setDeleteTarget({ kind: "dataset", name: workspace.name }); }} type="button"><Trash2 size={16} /> Xóa bộ dữ liệu</button></div>
            <section className="workspace-section">
              <h3>Bảng dữ liệu</h3>
              <div className="source-list">
                {(workspace.tables ?? []).map((table) => (
                  <UploadedTable key={`${workspace.dataset_id}-${table.dataset_table_id ?? table.display_name}`}
                    datasetId={workspace.dataset_id!} table={table} deletionDisabled={deletionDisabled}
                    onDelete={() => requestTableDelete(table)} />
                ))}
                {(workspace.tables ?? []).length === 0 ? <p className="empty-source">Chưa có bảng dữ liệu.</p> : null}
              </div>
              <label className="file-drop compact-drop" htmlFor="dataset-file">
                <UploadCloud size={21} /><span><strong>Thêm CSV hoặc XLSX</strong><small>{limits ? `Tối đa ${limits.max_file_bytes / 1048576} MB · ${limits.max_rows.toLocaleString("vi")} dòng · ${limits.max_columns} cột` : limitsError ?? "Đang đọc giới hạn từ máy chủ…"}</small></span>
                <input accept=".csv,.xlsx" id="dataset-file" onChange={(event) => { chooseTableFile(event.target.files?.[0] ?? null); event.target.value = ""; }} type="file" />
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
                    <button aria-label={`Xóa tài liệu ${document.original_filename}`} disabled={deletionDisabled} onClick={() => { setError(null); setDeleteTarget({ kind: "document", id: document.document_id, name: document.original_filename }); }} type="button"><Trash2 size={16} /></button>
                  </div>
                ))}
                {documents.length === 0 ? <p className="empty-source">Chưa có tài liệu.</p> : null}
              </div>
              <label className="file-drop compact-drop" htmlFor="document-file">
                <FileText size={21} /><span><strong>Thêm PDF, DOCX, TXT hoặc MD</strong><small>{limits ? `Tối đa ${limits.max_file_bytes / 1048576} MB · PDF ${limits.max_pdf_pages} trang có text layer; không OCR.` : "Đang đọc giới hạn tài liệu…"}</small>{limits && !limits.provider_data_enabled ? <small>Lưu tài liệu cần Gemini Embedding, hiện chưa được quản trị viên cho phép. CSV/XLSX vẫn nhập được bình thường.</small> : null}</span>
                <input accept=".pdf,.docx,.txt,.md" disabled={busy} id="document-file" onChange={(event) => { void addDocument(event.target.files?.[0] ?? null); event.target.value = ""; }} type="file" />
              </label>
            </section>
          </>
        ) : null}

        {workspace?.dataset_id && limits?.sql_join_v1_enabled && relationshipClient ? <RelationshipPanel
          key={JSON.stringify([workspace.dataset_id, workspace.tables])}
          client={relationshipClient}
          tables={(workspace.tables ?? []).filter((table) => table.dataset_table_id !== null).map((table) => ({ id: String(table.dataset_table_id), name: table.display_name, columns: table.columns }))}
        /> : null}
        </fieldset>
        {deleteTarget ? (
          <section aria-label="Xác nhận xóa dữ liệu" className="workspace-delete-confirm" ref={confirmation} tabIndex={-1}>
            <h3>Xóa {deleteTarget.kind === "dataset" ? "bộ dữ liệu" : deleteTarget.kind === "table" ? "bảng" : "tài liệu"} “{deleteTarget.name}”?</h3>
            <p>{deleteTarget.kind === "dataset"
              ? "Toàn bộ bảng, dữ liệu đã import, tài liệu và embeddings trong bộ này sẽ bị xóa vĩnh viễn. Các bộ dữ liệu khác không bị ảnh hưởng."
              : "Nguồn này và dữ liệu/embeddings tương ứng sẽ bị xóa vĩnh viễn. Lịch sử chat vẫn giữ các kết quả và trích đoạn đã lưu; chúng có thể không còn phản ánh nguồn hiện tại."}</p>
            {deleteTarget.kind === "dataset" ? <label className="workspace-delete-history"><input checked={deleteHistory} disabled={busy} onChange={(event) => setDeleteHistory(event.target.checked)} type="checkbox" />Xóa cả lịch sử chat gắn với bộ dữ liệu này (bắt buộc nếu đã có chat).</label> : null}
            <p>Không thể hoàn tác từ giao diện. File gốc trên máy của bạn không bị xóa.</p>
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <div className="dialog-actions">
              <button className="secondary-button" disabled={busy} onClick={() => { setDeleteTarget(null); setError(null); }} type="button">Hủy xóa</button>
              <button className="danger-button" disabled={busy || deletionDisabled} onClick={() => void confirmSourceDelete()} type="button">{busy ? "Đang xóa…" : "Xác nhận xóa vĩnh viễn"}</button>
            </div>
          </section>
        ) : null}
        {deletionDisabled ? <p role="status">Chờ yêu cầu chat hoàn tất trước khi xóa dữ liệu.</p> : null}

        <div className="dialog-actions"><button className="secondary-button" disabled={busy} onClick={onClose} type="button">Đóng</button>
          {workspace && ((workspace.table_count ?? 0) > 0 || (workspace.document_count ?? 0) > 0) ? <button className="primary-button" disabled={busy} onClick={onClose} type="button">Trò chuyện với dữ liệu</button> : null}
        </div>
      </div>
    </Modal>
  );
}
