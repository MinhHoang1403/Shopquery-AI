import { Check, ChevronDown, Database, FileSpreadsheet } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Dataset } from "../types";

interface DatasetSelectorProps {
  datasets: Dataset[];
  selectedDataset: Dataset | undefined;
  onSelect: (dataset: Dataset) => void;
}

export function DatasetSelector({ datasets, selectedDataset, onSelect }: DatasetSelectorProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function selectDataset(dataset: Dataset) {
    setOpen(false);
    onSelect(dataset);
  }

  return (
    <div className="dataset-selector" ref={root}>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Chọn bộ dữ liệu. Đang dùng ${selectedDataset?.name ?? "dữ liệu mặc định"}`}
        className="dataset-selector-button"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span>Dữ liệu:</span>
        <strong>{selectedDataset?.name ?? "Đang tải…"}</strong>
        <ChevronDown aria-hidden="true" size={14} />
      </button>

      {open ? (
        <div aria-label="Chọn bộ dữ liệu" className="dataset-menu" role="menu">
          <div className="dataset-menu-list">
            {datasets.map((dataset) => {
              const selected = dataset.dataset_id === selectedDataset?.dataset_id;
              return (
                <button
                  aria-checked={selected}
                  className={selected ? "dataset-option dataset-option--selected" : "dataset-option"}
                  key={dataset.dataset_id ?? "default"}
                  onClick={() => selectDataset(dataset)}
                  role="menuitemradio"
                  type="button"
                >
                  {dataset.kind === "default" ? <Database size={15} /> : <FileSpreadsheet size={15} />}
                  <span>
                    <strong>{dataset.name}</strong>
                    {dataset.kind === "uploaded" ? (
                      <small>{dataset.table_count ?? 0} bảng · {dataset.document_count ?? 0} tài liệu</small>
                    ) : <small>Dữ liệu E-commerce mẫu</small>}
                  </span>
                  {selected ? <Check className="dataset-option-check" size={15} /> : null}
                </button>
              );
            })}
          </div>

          {selectedDataset?.kind === "uploaded" ? (
            <details className="dataset-info">
              <summary>Xem thông tin dữ liệu</summary>
              <dl>
                <div><dt>Bảng</dt><dd>{selectedDataset.table_count ?? 0}</dd></div>
                <div><dt>Tài liệu</dt><dd>{selectedDataset.document_count ?? 0}</dd></div>
              </dl>
              <p>{selectedDataset.columns.map((column) => `${column.source_name}: ${column.data_type}`).join(" · ")}</p>
            </details>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
