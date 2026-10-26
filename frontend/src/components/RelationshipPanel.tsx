import { CheckCircle2, Link2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { DatasetColumn, RelationshipClient, RelationshipRecord } from "../types";

export interface RelationshipTableOption { id: string; name: string; columns: DatasetColumn[] }

export function RelationshipPanel({ tables, client }: {
  tables: RelationshipTableOption[]; client: Pick<RelationshipClient, "list">;
}) {
  const [state, setState] = useState<{ loading: boolean; records: RelationshipRecord[]; error: string }>({ loading: true, records: [], error: "" });
  const tableVersion = tables.map((table) => table.id).join(",");
  useEffect(() => {
    const controller = new AbortController();
    client.list(controller.signal).then((value) => {
      if (!controller.signal.aborted) setState({ loading: false, records: value.enabled ? value.relationships : [], error: "" });
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setState({ loading: false, records: [], error: reason instanceof Error ? reason.message : "Không tải được liên kết." });
    });
    return () => controller.abort();
  }, [client, tableVersion]);
  const active = state.records.filter((record) => record.valid);
  const linked = new Set(active.flatMap((record) => [record.source_table_id, record.target_table_id]));
  const tableName = (id: string) => tables.find((table) => table.id === id)?.name ?? "Nguồn không còn khả dụng";
  return <section className="workspace-section relationship-panel" aria-label="Liên kết dữ liệu">
    <div className="section-heading"><h3><Link2 size={16} aria-hidden="true" /> Liên kết dữ liệu</h3><span>{active.length} đang hoạt động</span></div>
    {state.loading ? <p role="status">Đang đọc liên kết…</p> : state.error ? <p role="alert" className="form-error">{state.error}</p> : <>
      <ul className="relationship-list">
        {active.map((record) => <li key={record.relationship_id}>
          <CheckCircle2 size={16} aria-hidden="true" />
          <div><strong>{tableName(record.source_table_id)}.{record.source_column} → {tableName(record.target_table_id)}.{record.target_column}</strong>
            <small>N:1 · Đã kiểm chứng{record.origin === "automatic" ? " · Tự động" : ""}</small>
          </div>
        </li>)}
      </ul>
      {tables.length > 1 && tables.some((table) => !linked.has(table.id)) ? <p className="empty-source">Có bảng chưa xác định được liên kết đáng tin cậy. Bạn vẫn có thể hỏi từng bảng riêng lẻ.</p> : null}
      {tables.length < 2 ? <p className="empty-source">Liên kết sẽ được kiểm chứng tự động khi bạn thêm bảng liên quan.</p> : null}
    </>}
  </section>;
}