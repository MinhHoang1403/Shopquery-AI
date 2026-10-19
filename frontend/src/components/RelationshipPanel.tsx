import { useEffect, useId, useState } from "react";
import type { DatasetColumn, RelationshipClient, RelationshipInput, RelationshipPreview, RelationshipRecord } from "../types";

export interface RelationshipTableOption { id: string; name: string; columns: DatasetColumn[] }

export function RelationshipPanel({ tables, client, disabled = false }: {
  tables: RelationshipTableOption[]; client: RelationshipClient; disabled?: boolean;
}) {
  const prefix = useId();
  const [selection, setSelection] = useState<RelationshipInput>({ source_table_id: "", source_column: "", target_table_id: "", target_column: "" });
  const [preview, setPreview] = useState<RelationshipPreview | null>(null);
  const [records, setRecords] = useState<RelationshipRecord[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    client.list(controller.signal).then((value) => {
      if (!controller.signal.aborted) { setEnabled(value.enabled); setRecords(value.relationships); }
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Không tải được liên kết."); });
    return () => controller.abort();
  }, [client]);

  function choose(field: keyof RelationshipInput, value: string) {
    setSelection((old) => ({ ...old, [field]: value,
      ...(field === "source_table_id" ? { source_column: "" } : {}),
      ...(field === "target_table_id" ? { target_column: "" } : {}),
    }));
    setPreview(null); setError(""); setDeleting(null);
  }
  async function action(operation: () => Promise<void>) {
    setBusy(true); setError("");
    try { await operation(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể xử lý liên kết."); }
    finally { setBusy(false); }
  }
  const tableName = (id: string) => tables.find((table) => table.id === id)?.name ?? "Nguồn đã bị xóa";
  return <details className="workspace-section relationship-panel">
    <summary>Liên kết bảng</summary>
    <p>V1: hai bảng, một khóa cùng kiểu, INNER JOIN chi tiết → danh mục. Chỉ dùng sau khi bạn xác nhận; không tự đoán quan hệ.</p>
    {error ? <p role="alert" className="form-error">{error}</p> : null}
    {!enabled ? <p role="status">Liên kết bảng chưa được bật hoặc chưa sẵn sàng.</p> : <fieldset disabled={busy || disabled}>
      <legend>Chọn quan hệ cần kiểm tra</legend>
      {(["source", "target"] as const).map((side) => {
        const field = `${side}_table_id` as const;
        const keyField = `${side}_column` as const;
        const selected = tables.find((item) => item.id === selection[field]);
        return <div className="relationship-fields" key={side}>
          <label className="field-label" htmlFor={`${prefix}-${side}-table`}>{side === "source" ? "Bảng chi tiết (fact)" : "Bảng danh mục (dimension)"}
            <select id={`${prefix}-${side}-table`} value={selection[field]} onChange={(event) => choose(field, event.target.value)}>
              <option value="">Chọn bảng</option>
              {tables.map((table) => <option key={table.id} value={table.id}>{table.name}</option>)}
            </select>
          </label>
          <label className="field-label" htmlFor={`${prefix}-${side}-column`}>{side === "source" ? "Khóa ở bảng chi tiết" : "Khóa ở bảng danh mục"}
            <select id={`${prefix}-${side}-column`} value={selection[keyField]} onChange={(event) => choose(keyField, event.target.value)}>
              <option value="">Chọn cột</option>
              {(selected?.columns ?? []).map((column) => <option key={column.name} value={column.name}>{column.source_name} · {column.data_type}</option>)}
            </select>
          </label>
        </div>;
      })}
      <button className="secondary-button" type="button" disabled={!Object.values(selection).every(Boolean)} onClick={() => void action(async () => { setPreview(null); setPreview(await client.preview(selection)); })}>Kiểm tra quan hệ</button>
      {preview ? <section aria-label="Kết quả kiểm tra quan hệ">
        <p>{tableName(preview.source_table_id)}.{preview.source_column} → {tableName(preview.target_table_id)}.{preview.target_column}</p>
        <dl>
          <dt>Loại quan hệ</dt><dd>{preview.cardinality ?? "Không hợp lệ"}</dd>
          <dt>Dòng chi tiết / danh mục</dt><dd>{preview.source_rows} / {preview.target_rows}</dd>
          <dt>Khóa trùng danh mục</dt><dd>{preview.target_duplicates}</dd>
          <dt>Khóa NULL chi tiết / danh mục</dt><dd>{preview.source_nulls} / {preview.target_nulls}</dd>
          <dt>Dòng thiếu khóa đích</dt><dd>{preview.orphan_rows ?? "Chưa kiểm tra được"}</dd>
        </dl>
        {preview.valid ? <>
          <p>Hợp lệ để xác nhận; chưa được kích hoạt. COUNT qua JOIN là số dòng chi tiết, không phải số đối tượng danh mục.</p>
          <button className="primary-button" type="button" onClick={() => void action(async () => {
            const record = await client.confirm({ ...selection, revision: preview.revision, confirmed: true });
            setRecords((old) => [...old.filter((item) => item.relationship_id !== record.relationship_id), record]); setPreview(null);
          })}>Xác nhận liên kết</button>
        </> : <div role="alert">{preview.reasons.map((reason) => <p key={reason}>{reason}</p>)}<p>Không được sử dụng trong v1.</p></div>}
      </section> : null}
      <h4>Liên kết đã xác nhận</h4>
      {records.length === 0 ? <p>Chưa có liên kết đã xác nhận.</p> : <ul>
        {records.map((item) => <li key={item.relationship_id}>
          <p>{tableName(item.source_table_id)}.{item.source_column} → {tableName(item.target_table_id)}.{item.target_column} · {item.valid ? item.cardinality : "Không còn hợp lệ"}</p>
          {!item.valid ? <p>{item.reasons.join(" ")}</p> : null}
          <button type="button" className="secondary-button" aria-label={`Xóa liên kết ${tableName(item.source_table_id)} đến ${tableName(item.target_table_id)}`} onClick={() => setDeleting(item.relationship_id)}>Xóa liên kết</button>
        </li>)}
      </ul>}
      {deleting ? <section aria-label="Xác nhận xóa liên kết">
        <p>Chỉ xóa liên kết; giữ nguyên dữ liệu bảng và lịch sử chat.</p>
        <button type="button" className="secondary-button" onClick={() => setDeleting(null)}>Hủy xóa liên kết</button>
        <button type="button" className="danger-button" onClick={() => void action(async () => { await client.remove(deleting); setRecords((old) => old.filter((item) => item.relationship_id !== deleting)); setDeleting(null); })}>Xác nhận xóa liên kết</button>
      </section> : null}
    </fieldset>}
  </details>;
}
