import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorDetails } from "./ErrorDetails";

afterEach(cleanup);

it("explains provider timeout without exposing diagnostic labels in the summary", () => {
  render(<ErrorDetails text="HTTP504 ProviderError" response={{
    answer:"HTTP504 ProviderError",error:"HTTP504 ProviderError",route:null,rows:[],sources:[],sql:null,
    error_context:{error_category:"timeout",origin_stage:"routing"},
  }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Dịch vụ AI chưa phản hồi kịp");
  expect(screen.queryByText(/HTTP504/)).not.toBeInTheDocument();
});

it("keeps one compact summary, toggles by keyboard and copies a bounded code", async () => {
  const user=userEvent.setup();
  const copy=vi.spyOn(navigator.clipboard,"writeText").mockResolvedValue();
  const code="a".repeat(32);
  render(<ErrorDetails text="Một lỗi" response={{ answer:"Một lỗi",error:"Một lỗi",route:null,
    rows:[],sources:[],sql:null,error_context:{correlation_id:code,origin_stage:"plan_binding",validation_branch:"unknown_source"} }} />);
  const button=screen.getByRole("button",{name:"Chi tiết lỗi"});
  expect(button).toHaveAttribute("aria-expanded","false");
  expect(screen.queryByText("Một lỗi")).not.toBeInTheDocument();
  button.focus(); await user.keyboard("{Enter}");
  expect(button).toHaveAttribute("aria-expanded","true");
  expect(screen.getAllByText("Một lỗi")).toHaveLength(1);
  await user.click(screen.getByRole("button",{name:"Sao chép mã hỗ trợ"}));
  expect(copy).toHaveBeenCalledWith(code);
  await user.click(button);
  expect(screen.queryByText("unknown_source")).not.toBeInTheDocument();
});

it("does not fabricate missing model, reason or support code", async () => {
  render(<ErrorDetails text="Lỗi cũ" />);
  await userEvent.setup().click(screen.getByRole("button",{name:"Chi tiết lỗi"}));
  expect(screen.queryByText("Model đã dùng")).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Sao chép mã hỗ trợ"})).not.toBeInTheDocument();
});
