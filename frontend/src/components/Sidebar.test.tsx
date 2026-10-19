import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

describe("Guest sidebar", () => {
  afterEach(cleanup);
  it.each([false, true])("keeps uploads without duplicating login, collapsed=%s", (collapsed) => {
    const onUpload = vi.fn();
    render(<Sidebar
      guest
      open
      collapsed={collapsed}
      conversations={[]}
      activeConversationId={null}
      onClose={vi.fn()}
      onToggleCollapse={vi.fn()}
      onNewChat={vi.fn()}
      onSelectConversation={vi.fn()}
      onRename={vi.fn()}
      onDelete={vi.fn()}
      onUpload={onUpload}
    />);

    expect(screen.queryByRole("button", { name: "Đăng nhập" })).not.toBeInTheDocument();
    expect(screen.queryByText("Đăng nhập để lưu lịch sử và bộ dữ liệu.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tệp tạm thời" }));
    expect(onUpload).toHaveBeenCalledOnce();
  });
});
