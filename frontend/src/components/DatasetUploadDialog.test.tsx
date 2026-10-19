import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import type { Dataset } from "../types";
import { DatasetUploadDialog } from "./DatasetUploadDialog";

vi.mock("../api", () => ({
  createDataset: vi.fn(), deleteDataset: vi.fn(), deleteDatasetTable: vi.fn(),
  deleteDatasetDocument: vi.fn(), getDataset: vi.fn(), getDatasetDocuments: vi.fn(),
  importDataset: vi.fn(), importDatasetTable: vi.fn(), previewDataset: vi.fn(),
  uploadDatasetDocument: vi.fn(),
  getUploadLimits: vi.fn(),
}));

const workspace: Dataset = {
  dataset_id: 7, kind: "uploaded", name: "Học phí", original_filename: "fees.csv",
  file_type: "csv", sheet_name: null, row_count: 2, column_count: 1, columns: [],
  created_at: null, table_count: 1, document_count: 1,
  tables: [{ dataset_table_id: 12, display_name: "Học viên", original_filename: "fees.csv",
    file_type: "csv", sheet_name: null, row_count: 2, column_count: 1, columns: [] }],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getUploadLimits).mockResolvedValue({ max_file_bytes: 10485760, max_rows: 5000, max_columns: 30, max_pdf_pages: 100, provider_data_enabled: false, preview_per_hour: 180, upload_per_hour: 60 });
  vi.mocked(api.getDataset).mockResolvedValue(workspace);
  vi.mocked(api.getDatasetDocuments).mockResolvedValue([{
    document_id: 4, dataset_id: 7, original_filename: "policy.md", file_type: "md",
    title: "Quy định", chunk_count: 3, created_at: "2026-10-19T00:00:00Z",
  }]);
});
afterEach(cleanup);

async function openManager(deletionDisabled = false) {
  const onImported = vi.fn();
  const onDeleted = vi.fn();
  const user = userEvent.setup();
  render(<DatasetUploadDialog datasets={[workspace]} deletionDisabled={deletionDisabled}
    onClose={vi.fn()} onDeleted={onDeleted} onImported={onImported} />);
  await user.click(screen.getByRole("tab", { name: "Quản lý bộ hiện có" }));
  await screen.findByText("policy.md");
  return { user, onImported, onDeleted };
}

describe("workspace deletion", () => {
  it("requires confirmation and cancellation does not send DELETE", async () => {
    const { user } = await openManager();
    await user.click(screen.getByRole("button", { name: "Xóa bảng Học viên" }));
    expect(screen.getByText(/Lịch sử chat vẫn giữ/)).toBeInTheDocument();
    expect(api.deleteDatasetTable).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Hủy xóa" }));
    expect(api.deleteDatasetTable).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Xác nhận xóa dữ liệu" })).not.toBeInTheDocument();
  });

  it("deletes only the selected table and updates metadata immediately", async () => {
    const { user, onImported, onDeleted } = await openManager();
    await user.click(screen.getByRole("button", { name: "Xóa bảng Học viên" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    expect(api.deleteDatasetTable).toHaveBeenCalledExactlyOnceWith(7, 12);
    expect(screen.queryByRole("button", { name: "Xóa bảng Học viên" })).not.toBeInTheDocument();
    expect(screen.getByText("policy.md")).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledWith(expect.objectContaining({
      table_count: 0, tables: [], original_filename: null, row_count: null, document_count: 1,
    }));
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("deletes a document without deleting tables or workspace", async () => {
    const { user, onImported } = await openManager();
    await user.click(screen.getByRole("button", { name: "Xóa tài liệu policy.md" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    expect(api.deleteDatasetDocument).toHaveBeenCalledExactlyOnceWith(7, 4);
    expect(screen.queryByText("policy.md")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xóa bảng Học viên" })).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledWith(expect.objectContaining({ document_count: 0, table_count: 1 }));
    expect(api.deleteDataset).not.toHaveBeenCalled();
  });

  it("keeps sources on failure and requires explicit consent to delete history", async () => {
    vi.mocked(api.deleteDataset).mockRejectedValueOnce(new Error("Bộ dữ liệu có lịch sử chat."));
    const { user, onDeleted } = await openManager();
    await user.click(screen.getByRole("button", { name: "Xóa bộ dữ liệu" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    expect(api.deleteDataset).toHaveBeenLastCalledWith(7, false);
    expect(await screen.findByRole("alert")).toHaveTextContent("Bộ dữ liệu có lịch sử chat.");
    expect(screen.getByText("policy.md")).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox", { name: /Xóa cả lịch sử chat/ }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    expect(api.deleteDataset).toHaveBeenLastCalledWith(7, true);
    expect(onDeleted).toHaveBeenCalledWith(workspace);
    expect(screen.queryByText("policy.md")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Bộ dữ liệu" })).toHaveValue("");
  });

  it("blocks duplicate requests and changing workspace during deletion", async () => {
    let resolveDelete: () => void = () => {};
    vi.mocked(api.deleteDatasetTable).mockImplementation(() => new Promise<void>((resolve) => {
      resolveDelete = resolve;
    }));
    const { user } = await openManager();
    await user.click(screen.getByRole("button", { name: "Xóa bảng Học viên" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    expect(screen.getByRole("button", { name: "Đang xóa…" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Bộ dữ liệu" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hủy xóa" })).toBeDisabled();
    expect(api.deleteDatasetTable).toHaveBeenCalledTimes(1);
    resolveDelete();
    await waitFor(() => expect(screen.queryByText("Đang xóa…")).not.toBeInTheDocument());
  });

  it("disables deletion while chat is running", async () => {
    await openManager(true);
    expect(screen.getByRole("button", { name: "Xóa bộ dữ liệu" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Xóa bảng Học viên" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Xóa tài liệu policy.md" })).toBeDisabled();
  });
});
