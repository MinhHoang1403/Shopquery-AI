import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import type { ChatResponse } from "../types";
import { ChatMessage } from "./ChatMessage";

afterEach(cleanup);

function response(): ChatResponse {
  return {
    answer: "Đã tổng hợp dữ liệu. Mở bảng để xem chi tiết.", route: "SQL",
    sql: "SELECT id, amount FROM evidence", sources: [], error: null,
    rows: [{ id: "000019", amount: "9007199254740993.05", date: "2032-04-09", missing: null }],
    result_columns: [{ key: "amount", label: "Tổng", numeric: true }],
  };
}

it("keeps structured rows collapsed and exposes one accessible detail table", async () => {
  const data = response();
  render(<ChatMessage entry={{ id: "a", role: "assistant", text: data.answer, response: data }} />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  const button = screen.getByRole("button", { name: "Xem bảng dữ liệu · 1 dòng" });
  expect(button).toHaveAttribute("aria-expanded", "false");
  const user = userEvent.setup();
  button.focus();
  await user.keyboard("{Enter}");
  expect(screen.getAllByRole("table")).toHaveLength(1);
  expect(screen.getByRole("cell", { name: "000019" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "9.007.199.254.740.993,05" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "2032-04-09" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "—" })).toBeVisible();
  await user.click(button);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Xem truy vấn SQL" }));
  expect(screen.getByText(data.sql!)).toBeVisible();
});

it("marks legacy Hybrid conclusions without trusted verification as unverified", () => {
  const data = response();
  data.route = "HYBRID";
  render(<ChatMessage entry={{ id: "a", role: "assistant", text: data.answer, response: data }} />);
  expect(screen.getByText("Chưa xác minh kết luận")).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
