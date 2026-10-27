import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import { ChatMessage } from "./ChatMessage";
import type { ChatResponse } from "../types";

afterEach(cleanup);

function answer(size: number): ChatResponse {
  return {
    answer: "Kết quả:", route: "SQL", sql: "SELECT ...", error: null, sources: [],
    rows: Array.from({ length: size }, (_, i) => ({
      id: `KS${String(i).padStart(3, "0")}`, code: "000123", date: 20261026,
      amount: "12345678901234567890.12", zero: "0.00", missing: null,
    })),
    result_columns: [
      { key: "amount", label: "Tổng tiền", numeric: true },
      { key: "zero", label: "Số không", numeric: true },
    ],
  };
}

it("uses verified Hybrid selection and retains full SQL evidence in the same panel", async () => {
  const response = answer(12);
  response.route = "HYBRID";
  response.verification_status = "verified_classification";
  response.answer_row_indices = [0, 1, 2, 3, 4, 5];
  render(<ChatMessage entry={{ id: "a", role: "assistant", text: "Chưa đạt: KS000–KS005", response }} />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Xem bảng dữ liệu/ }));
  expect(screen.getAllByRole("row")).toHaveLength(7);
  expect(screen.queryByRole("cell", { name: "KS006" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Xem toàn bộ 12 dòng bằng chứng SQL" }));
  expect(screen.getAllByRole("row")).toHaveLength(13);
  expect(screen.getByRole("cell", { name: "KS006" })).toBeVisible();
  expect(screen.getAllByRole("table")).toHaveLength(1);
});

it.each([12, 16])("opens all %i rows with exact metrics and untouched codes", async (size) => {
  const response = JSON.parse(JSON.stringify(answer(size)));
  render(<ChatMessage entry={{ id: "a", role: "assistant", text: response.answer, response }} />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  const button = screen.getByRole("button", { name: /Xem bảng dữ liệu/ });
  expect(button).toHaveAttribute("aria-expanded", "false");
  const user = userEvent.setup();
  await user.click(button);
  expect(screen.getAllByRole("row")).toHaveLength(size + 1);
  for (const value of ["000123", "20261026", "12.345.678.901.234.567.890,12", "0,00", "—"]) {
    expect(screen.getAllByRole("cell", { name: value })).toHaveLength(size);
  }
  expect(screen.getAllByRole("table")).toHaveLength(1);
  await user.click(button);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("paginates 200 detail rows and restores a collapsed panel without duplicates", async () => {
  const response = answer(200);
  render(<ChatMessage entry={{ id: "a", role: "assistant", text: response.answer, response }} />);
  const user = userEvent.setup();
  const button = screen.getByRole("button", { name: /Xem bảng dữ liệu/ });
  await user.click(button);
  expect(screen.getAllByRole("row")).toHaveLength(21);
  await user.click(screen.getByRole("button", { name: "Tiếp" }));
  expect(screen.getByRole("cell", { name: "KS020" })).toBeVisible();
  expect(screen.getAllByRole("row")).toHaveLength(21);
  await user.click(button);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  await user.click(button);
  expect(screen.getByRole("cell", { name: "KS000" })).toBeVisible();
  expect(screen.getAllByRole("table")).toHaveLength(1);
});

it("keeps legacy history conservative, ignores unverified selection and escapes cells", async () => {
  const response = answer(2);
  delete response.result_columns;
  response.route = "HYBRID";
  response.answer_row_indices = [0];
  response.rows = [
    { id: "000123", amount: "100.00", name: "<img src=x onerror=alert(1)>" },
    { id: "000124", amount: "0.00", name: "Other" },
  ];
  const { container } = render(<ChatMessage entry={{ id: "a", role: "assistant", text: response.answer, response }} />);
  await userEvent.setup().click(screen.getByRole("button", { name: /Xem bảng dữ liệu/ }));
  expect(screen.getByRole("cell", { name: "100.00" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "000123" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "000124" })).toBeVisible();
  expect(container.querySelector("img,script")).toBeNull();
});
