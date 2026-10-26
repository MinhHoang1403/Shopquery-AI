import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RelationshipPanel } from "./RelationshipPanel";
import type { RelationshipClient, RelationshipRecord } from "../types";
afterEach(cleanup);
const tables = [
  { id: "1", name: "payments", columns: [] }, { id: "2", name: "students", columns: [] },
];
const record: RelationshipRecord = {
  source_table_id: "1", source_column: "student_id", target_table_id: "2", target_column: "id",
  revision: "a".repeat(64), valid: true, cardinality: "many-to-one", source_rows: 3, target_rows: 2,
  source_nulls: 0, target_nulls: 0, target_duplicates: 0, orphan_rows: 0, reasons: [],
  relationship_id: "automatic", confirmed: false, origin: "automatic",
};
function client(): RelationshipClient {
  return { list: vi.fn().mockResolvedValue({ enabled: true, relationships: [record] }),
    preview: vi.fn(), confirm: vi.fn(), remove: vi.fn(), discover: vi.fn() };
}
it("lists verified links without any mutating controls or discovery calls", async () => {
  const api = client();
  const view = render(<RelationshipPanel tables={tables} client={api} />);
  expect(await screen.findByText(/payments.student_id → students.id/)).toBeInTheDocument();
  expect(screen.getByText(/N:1 · Đã kiểm chứng · Tự động/)).toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  view.rerender(<RelationshipPanel tables={[...tables]} client={api} />);
  expect(api.list).toHaveBeenCalledTimes(1);
  expect(api.discover).not.toHaveBeenCalled(); expect(api.preview).not.toHaveBeenCalled();
  expect(api.confirm).not.toHaveBeenCalled(); expect(api.remove).not.toHaveBeenCalled();
});
it("explains unlinked tables without proposing unsafe links", async () => {
  const api = client(); vi.mocked(api.list).mockResolvedValue({ enabled: true, relationships: [] });
  render(<RelationshipPanel tables={tables} client={api} />);
  expect(await screen.findByText(/Có bảng chưa xác định được liên kết đáng tin cậy/)).toBeInTheDocument();
});
it("aborts pending reads and ignores late workspace responses", async () => {
  let resolve: (value: Awaited<ReturnType<RelationshipClient["list"]>>) => void = () => {};
  const api = client(); vi.mocked(api.list).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  const view = render(<RelationshipPanel tables={tables} client={api} />);
  const signal = vi.mocked(api.list).mock.calls[0][0];
  view.unmount(); expect(signal?.aborted).toBe(true);
  resolve({ enabled: true, relationships: [record] });
  const next = client(); vi.mocked(next.list).mockResolvedValue({ enabled: true, relationships: [] });
  render(<RelationshipPanel tables={tables} client={next} />);
  await waitFor(() => expect(screen.queryByText(/payments.student_id/)).not.toBeInTheDocument());
});