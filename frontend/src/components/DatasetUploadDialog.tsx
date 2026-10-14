import { AlertCircle, CheckCircle2, FileSpreadsheet, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { importDataset, previewDataset } from "../api";
import type { Dataset, DatasetPreview } from "../types";
import { ResultTable } from "./ResponseEvidence";
import { Modal } from "./Dialogs";

interface DatasetUploadDialogProps {
  onClose: () => void;
  onImported: (dataset: Dataset) => void;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Không thể xử lý file.";
}

export function DatasetUploadDialog({ onClose, onImported }: DatasetUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [selectedSheet, setSelectedSheet] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const previewController = useRef<AbortController | null>(null);

  useEffect(() => () => previewController.current?.abort(), []);

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

  function chooseFile(selectedFile: File | null) {
    setFile(selectedFile);
    setPreview(null);
    setSelectedSheet(null);
    setError(null);
    if (!selectedFile) return;
    setDatasetName(selectedFile.name.replace(/\.(csv|xlsx)$/i, "").slice(0, 120));
    void loadPreview(selectedFile);
  }

  async function confirmImport() {
    if (!file || !preview || !datasetName.trim()) return;
    setIsImporting(true);
    setError(null);
    try {
      const dataset = await importDataset(file, datasetName.trim(), selectedSheet);
      onImported(dataset);
    } catch (importError) {
      setError(messageFromError(importError));
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <Modal
      title="Nạp dữ liệu mới"
      description="Kiểm tra bản xem trước trước khi dữ liệu được lưu vào PostgreSQL."
      onClose={onClose}
    >
      <div className="upload-flow">
        <label className="file-drop" htmlFor="dataset-file">
          <UploadCloud size={25} />
          <span><strong>Chọn file CSV hoặc XLSX</strong><small>Tối đa 10 MB · 5.000 dòng · 30 cột</small></span>
          <input
            accept=".csv,.xlsx"
            id="dataset-file"
            onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>

        {file ? (
          <div className="selected-file">
            <FileSpreadsheet size={18} />
            <span><strong>{file.name}</strong><small>{(file.size / 1024).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} KB</small></span>
            {preview ? <CheckCircle2 className="success-icon" size={18} /> : null}
          </div>
        ) : null}

        {isPreviewing ? <div className="upload-status" role="status">Đang kiểm tra file…</div> : null}
        {error ? <p className="form-error upload-error" role="alert"><AlertCircle size={16} /> {error}</p> : null}

        {preview ? (
          <div className="preview-panel">
            <div className="preview-stats">
              <span><strong>{preview.row_count.toLocaleString("vi-VN")}</strong> dòng</span>
              <span><strong>{preview.column_count}</strong> cột</span>
              <span><strong>{preview.file_type.toUpperCase()}</strong> định dạng</span>
            </div>
            {preview.sheet_names.length > 1 ? (
              <label className="field-label" htmlFor="sheet-select">Sheet
                <select
                  id="sheet-select"
                  onChange={(event) => { setSelectedSheet(event.target.value); if (file) void loadPreview(file, event.target.value); }}
                  value={selectedSheet ?? ""}
                >
                  {preview.sheet_names.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
            ) : null}
            <div className="column-summary">
              {preview.columns.map((column) => (
                <span key={column.name}><strong>{column.source_name}</strong><small>{column.data_type}</small></span>
              ))}
            </div>
            {preview.warnings.map((warning) => <p className="upload-warning" key={warning}>{warning}</p>)}
            <ResultTable rows={preview.rows} />
            <label className="field-label" htmlFor="dataset-name">Tên bộ dữ liệu
              <input id="dataset-name" maxLength={120} onChange={(event) => setDatasetName(event.target.value)} value={datasetName} />
            </label>
          </div>
        ) : null}

        <div className="dialog-actions">
          <button className="secondary-button" disabled={isImporting} onClick={onClose} type="button">Hủy</button>
          <button className="primary-button" disabled={!preview || !datasetName.trim() || isImporting || isPreviewing} onClick={confirmImport} type="button">
            {isImporting ? "Đang import…" : "Xác nhận import"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
