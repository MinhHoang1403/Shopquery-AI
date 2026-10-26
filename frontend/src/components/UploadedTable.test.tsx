import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getDatasetTablePreview } from "../api";
import { UploadedTable } from "./UploadedTable";
import type { DatasetTablePreview } from "../types";

vi.mock("../api", () => ({ getDatasetTablePreview: vi.fn() }));
afterEach(cleanup);
const preview: DatasetTablePreview = {
  dataset_table_id: 12, display_name: "Phí", original_filename: "fees.csv", file_type: "csv",
  sheet_name: null, row_count: 3, column_count: 2,
  columns: [{ name: "name", source_name: "Tên", data_type: "TEXT" }, { name: "fee", source_name: "Phí", data_type: "NUMERIC" }],
  rows: [{ "Tên": "<script>alert(1)</script>", "Phí": "9007199254740993.01" }, { "Tên": "Tiếng Việt", "Phí": null }, { "Tên": "Zero", "Phí": "0.00" }],
};
beforeEach(() => { vi.resetAllMocks(); vi.mocked(getDatasetTablePreview).mockResolvedValue(preview); });
it("loads only the expanded table, preserves exact cells and keeps delete separate", async () => {
  const user = userEvent.setup(); const remove = vi.fn();
  render(<><UploadedTable datasetId={7} table={preview} onDelete={remove} /><UploadedTable datasetId={7} table={{ ...preview, dataset_table_id: 13, display_name: "Khác" }} onDelete={remove} /></>);
  expect(getDatasetTablePreview).not.toHaveBeenCalled();
  const button = screen.getByRole("button", { name: "Xem dữ liệu Phí" });
  expect(button).toHaveAttribute("aria-expanded", "false");
  button.focus(); await user.keyboard("{Enter}");
  expect(await screen.findByText("9007199254740993.01")).toBeInTheDocument();
  expect(screen.getByText("0.00")).toBeInTheDocument(); expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(getDatasetTablePreview).toHaveBeenCalledExactlyOnceWith(7, 12, expect.any(AbortSignal));
  expect(remove).not.toHaveBeenCalled();
  await user.click(button); expect(button).toHaveAttribute("aria-expanded", "false");
  await user.click(button); expect(getDatasetTablePreview).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Xóa bảng Phí" })); expect(remove).toHaveBeenCalledTimes(1);
});
it("shows loading, aborts on collapse/unmount and ignores late values across workspace changes", async () => {
  let resolve: (value: DatasetTablePreview) => void = () => {};
  vi.mocked(getDatasetTablePreview).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  const user = userEvent.setup(); const view = render(<UploadedTable datasetId={7} table={preview} onDelete={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Xem dữ liệu Phí" }));
  expect(screen.getByRole("status")).toHaveTextContent("Đang đọc");
  const signal = vi.mocked(getDatasetTablePreview).mock.calls[0][2];
  view.unmount(); expect(signal?.aborted).toBe(true);
  resolve(preview);
  render(<UploadedTable datasetId={8} table={{ ...preview, dataset_table_id: 20, display_name: "Mới" }} onDelete={vi.fn()} />);
  expect(screen.queryByText("9007199254740993.01")).not.toBeInTheDocument();
});
it("shows recoverable error and empty states with registered headers", async () => {
  const user = userEvent.setup(); vi.mocked(getDatasetTablePreview).mockRejectedValueOnce(new Error("Không thể đọc"));
  render(<UploadedTable datasetId={7} table={preview} onDelete={vi.fn()} />);
  const button = screen.getByRole("button", { name: "Xem dữ liệu Phí" });
  await user.click(button); expect(await screen.findByRole("alert")).toHaveTextContent("Không thể đọc");
  await user.click(button); vi.mocked(getDatasetTablePreview).mockResolvedValue({ ...preview, rows: [] });
  await user.click(button); await waitFor(() => expect(screen.getByText("Chưa có dòng dữ liệu.")).toBeInTheDocument());
  expect(screen.getByRole("columnheader", { name: "Tên" })).toBeInTheDocument();
});
