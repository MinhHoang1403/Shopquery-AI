import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { RelationshipPanel } from "./RelationshipPanel";
import type { RelationshipClient, RelationshipPreview } from "../types";

afterEach(cleanup);
const tables = [
  { id: "fact", name: "payments", columns: [{ source_name: "Mã học viên", name: "student_id", data_type: "BIGINT" }] },
  { id: "dim", name: "students", columns: [{ source_name: "Mã", name: "id", data_type: "BIGINT" }] },
];
const preview: RelationshipPreview = {
  source_table_id: "fact", source_column: "student_id", target_table_id: "dim", target_column: "id",
  revision: "a".repeat(64), valid: true, cardinality: "many-to-one", source_rows: 3, target_rows: 2,
  source_nulls: 0, target_nulls: 0, target_duplicates: 0, orphan_rows: 0, reasons: [],
};
function client(valid = true): RelationshipClient {
  return {
    list: vi.fn().mockResolvedValue({ enabled: true, relationships: [] }),
    preview: vi.fn().mockResolvedValue({ ...preview, valid, reasons: valid ? [] : ["Khóa đích bị trùng"] }),
    confirm: vi.fn().mockResolvedValue({ ...preview, relationship_id: "confirmed", confirmed: true }),
    remove: vi.fn().mockResolvedValue(undefined),
    discover: vi.fn().mockResolvedValue({ relationships: [], suggestions: [], truncated: false }),
  };
}
async function choose() {
  const user = userEvent.setup();
  await user.click(screen.getByText("Liên kết bảng", { exact: true }));
  await user.selectOptions(await screen.findByLabelText("Bảng chi tiết (fact)"), "fact");
  await user.selectOptions(screen.getByLabelText("Khóa ở bảng chi tiết"), "student_id");
  await user.selectOptions(screen.getByLabelText("Bảng danh mục (dimension)"), "dim");
  await user.selectOptions(screen.getByLabelText("Khóa ở bảng danh mục"), "id");
  await user.click(screen.getByRole("button", { name: "Kiểm tra quan hệ" }));
  return user;
}
it("requires explicit confirmation, then explicit deletion without deleting tables", async () => {
  const api = client(); render(<RelationshipPanel tables={tables} client={api} />);
  const user = await choose();
  const confirm = await screen.findByRole("button", { name: "Xác nhận liên kết" });
  expect(api.confirm).not.toHaveBeenCalled();
  await user.click(confirm);
  expect(api.confirm).toHaveBeenCalledWith({
    source_table_id: "fact", source_column: "student_id", target_table_id: "dim", target_column: "id",
    revision: preview.revision, confirmed: true,
  });
  await user.click(await screen.findByRole("button", { name: "Xóa liên kết payments đến students" }));
  expect(api.remove).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Hủy xóa liên kết" }));
  expect(api.remove).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Xóa liên kết payments đến students" }));
  await user.click(screen.getByRole("button", { name: "Xác nhận xóa liên kết" }));
  expect(api.remove).toHaveBeenCalledWith("confirmed");
  expect(screen.getAllByRole("option", { name: "payments" })).toHaveLength(2);
});
it("blocks invalid keys and clears stale preview when selection changes", async () => {
  const api = client(false); render(<RelationshipPanel tables={tables} client={api} />);
  const user = await choose();
  expect(await screen.findByText("Khóa đích bị trùng")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Xác nhận liên kết" })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Bảng chi tiết (fact)"), "dim");
  expect(screen.queryByLabelText("Kết quả kiểm tra quan hệ")).not.toBeInTheDocument();
  expect(api.confirm).not.toHaveBeenCalled();
});
it("does not advertise active relationships when the flag is off", async () => {
  const api = client(); vi.mocked(api.list).mockResolvedValue({ enabled: false, relationships: [] });
  render(<RelationshipPanel tables={tables} client={api} />);
  expect(await screen.findByText("Liên kết bảng chưa được bật hoặc chưa sẵn sàng.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Kiểm tra quan hệ" })).not.toBeInTheDocument();
});

it("refreshes automatic links after upload without pretending the user confirmed", async () => {
  const api = client();
  const view = render(<RelationshipPanel tables={[tables[0]]} client={api} />);
  await userEvent.click(screen.getByText("Liên kết bảng", { exact: true }));
  expect(await screen.findByText(/Chưa có liên kết hợp lệ/)).toBeVisible();
  vi.mocked(api.list).mockResolvedValue({ enabled: true, relationships: [
    { ...preview, relationship_id: "automatic", confirmed: false, origin: "automatic" },
  ] });
  view.rerender(<RelationshipPanel tables={tables} client={api} />);
  expect(await screen.findByText("Tự động kiểm chứng từ tên khóa và toàn bộ dữ liệu")).toBeVisible();
  expect(screen.queryByText("Bạn đã xác nhận")).not.toBeInTheDocument();
  expect(api.confirm).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Xóa liên kết payments đến students" }));
  expect(api.remove).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Xác nhận xóa liên kết" }));
  expect(api.remove).toHaveBeenCalledWith("automatic");
});

it("rescans old uploads and displays automatic activation without manual confirmation", async () => {
  const api = client();
  vi.mocked(api.discover!).mockResolvedValue({ relationships: [
    { ...preview, relationship_id: "found", confirmed: false, origin: "automatic" },
  ], suggestions: [], truncated: false });
  render(<RelationshipPanel tables={tables} client={api} />);
  await userEvent.click(screen.getByText("Liên kết bảng", { exact: true }));
  await userEvent.click(await screen.findByRole("button", { name: "Tự tìm liên kết" }));
  expect(await screen.findByText(/Quét xong: 1 liên kết đang hoạt động/)).toBeVisible();
  expect(screen.getByText("Tự động kiểm chứng từ tên khóa và toàn bộ dữ liệu")).toBeVisible();
  expect(api.confirm).not.toHaveBeenCalled();
});

it("keeps uncertain suggestions inactive and rechecks before offering confirmation", async () => {
  const api = client();
  vi.mocked(api.discover!).mockResolvedValue({ relationships: [], truncated: false, suggestions: [
    { relationship: { source_table_id: "fact", source_column: "student_id", target_table_id: "dim", target_column: "id" }, preview, reason: "Có ứng viên cạnh tranh." },
  ] });
  render(<RelationshipPanel tables={tables} client={api} />);
  await userEvent.click(screen.getByText("Liên kết bảng", { exact: true }));
  await userEvent.click(await screen.findByRole("button", { name: "Tự tìm liên kết" }));
  expect(await screen.findByText("Có ứng viên cạnh tranh.")).toBeVisible();
  expect(api.confirm).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Kiểm tra gợi ý" }));
  expect(await screen.findByRole("button", { name: "Xác nhận liên kết" })).toBeVisible();
  expect(api.preview).toHaveBeenCalledOnce();
  expect(api.confirm).not.toHaveBeenCalled();
});

it("reports scan failures and leaves existing links intact", async () => {
  const api = client();
  vi.mocked(api.discover!).mockRejectedValue(new Error("Không thể quét."));
  render(<RelationshipPanel tables={tables} client={api} />);
  await userEvent.click(screen.getByText("Liên kết bảng", { exact: true }));
  await userEvent.click(await screen.findByRole("button", { name: "Tự tìm liên kết" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Không thể quét.");
  expect(api.confirm).not.toHaveBeenCalled();
});
