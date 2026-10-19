import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

afterEach(cleanup);

it("uses authenticated name/email and opens a keyboard-accessible logout menu", async () => {
  const logout = vi.fn();
  render(<AccountMenu account={{ user_id: "A", display_name: "Nguyễn An", email: "an@example.invalid" }} onLogout={logout} />);
  expect(screen.getByText("Nguyễn An")).toBeInTheDocument();
  expect(screen.getByText("an@example.invalid")).toBeInTheDocument();
  const user = userEvent.setup();
  const trigger = screen.getByRole("button", { name: "Mở menu tài khoản" });
  trigger.focus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("menuitem", { name: "Đăng xuất" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  await user.click(trigger);
  await user.click(screen.getByRole("menuitem", { name: "Đăng xuất" }));
  expect(logout).toHaveBeenCalledOnce();
});

it("closes on outside pointer and tabbing away", async () => {
  render(<><AccountMenu account={{ user_id: "A", display_name: "A", email: "a@example.invalid" }} onLogout={vi.fn()} /><button>Outside</button></>);
  const user = userEvent.setup();
  const trigger = screen.getByRole("button", { name: "Mở menu tài khoản" });
  await user.click(trigger);
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  await user.click(trigger);
  await user.tab();
  expect(screen.getByRole("button", { name: "Outside" })).toHaveFocus();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});
