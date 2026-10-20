import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatMessage } from "./ChatMessage";
import { ModelSelector } from "./ModelSelector";

afterEach(cleanup);

function renderAnswer(text: string) {
  return render(<ChatMessage entry={{ id: "answer", role: "assistant", text }} />);
}

describe("Assistant content", () => {
  it("renders the old generic refusal kindly without rewriting restored history", () => {
    const text = "Bộ dữ liệu không có đủ loại nguồn để trả lời câu hỏi này. Nếu cần ghép hai bảng, hãy kiểm tra Quản lý dữ liệu → Liên kết bảng. JOIN v1 chỉ hỗ trợ hai bảng với quan hệ đã xác nhận và tổng hợp fact an toàn.";
    const entry = { id: "legacy", role: "assistant" as const, text,
      response: { answer: text, route: "UNSUPPORTED" as const, sql: null, rows: [], sources: [], error: null } };
    render(<ChatMessage entry={entry} />);
    expect(screen.queryByText(text)).not.toBeInTheDocument();
    expect(screen.getByText("Mình chưa đủ thông tin để trả lời chính xác câu hỏi này. Bạn hãy kiểm tra dữ liệu hoặc liên kết bảng trong Quản lý dữ liệu nhé.")).toBeVisible();
    expect(entry.text).toBe(text);
    expect(entry.response.answer).toBe(text);
  });

  it("labels a persisted unsupported data answer without claiming it is out of scope", () => {
    const answer = "Mình chưa đủ thông tin để trả lời chính xác câu hỏi này. Bạn hãy kiểm tra dữ liệu hoặc liên kết bảng trong Quản lý dữ liệu nhé.";
    render(<ChatMessage entry={{ id: "restored", role: "assistant", text: answer,
      response: { answer, route: "UNSUPPORTED", sql: null, rows: [], sources: [], error: null } }} />);
    expect(screen.getByText("Chưa thể trả lời")).toBeVisible();
    expect(screen.queryByText("Ngoài phạm vi")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Bằng chứng hỗ trợ" })).not.toBeInTheDocument();
    expect(screen.getByText(answer)).toBeVisible();
  });

  it("renders paragraphs, lists, emphasis and code without changing their content", () => {
    const { container } = renderAnswer("Tóm tắt **doanh số**.\n\n1. Áo linen\n2. Túi vải\n\n- Đổi trả\n- Vận chuyển\n\nCột `quantity`.\n\n```sql\nSELECT name FROM products;\n```");
    expect(container.querySelector("strong")?.textContent).toBe("ShopQuery AI");
    expect(screen.getByText("doanh số").tagName).toBe("STRONG");
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(screen.getByText("quantity").tagName).toBe("CODE");
    expect(container.querySelector("pre code")?.textContent).toBe("SELECT name FROM products;\n");
    expect(container.querySelector("pre")).toHaveAttribute("tabindex", "0");
  });

  it("renders GFM tables in a keyboard-accessible scroll region", () => {
    renderAnswer("| Sản phẩm | Số lượng |\n| --- | --- |\n| Áo linen | 42 |");
    const region = screen.getByRole("region", { name: "Bảng trong câu trả lời" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.querySelector("table")).not.toBeNull();
    expect(screen.getByRole("columnheader", { name: "Sản phẩm" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "Áo linen" })).toBeVisible();
  });

  it("keeps plain Vietnamese text readable without inventing evidence", () => {
    renderAnswer("Cửa hàng tiếp nhận đổi trả trong 14 ngày.\n\nVui lòng giữ hóa đơn.");
    expect(screen.getByText("Cửa hàng tiếp nhận đổi trả trong 14 ngày.")).toBeVisible();
    expect(screen.getByText("Vui lòng giữ hóa đơn.")).toBeVisible();
    expect(screen.queryByRole("group", { name: "Bằng chứng hỗ trợ" })).not.toBeInTheDocument();
  });

  it("ignores raw HTML and does not load Markdown images or execute embedded code", () => {
    const { container } = renderAnswer('<script>alert("xss")</script>\n\n<img src="x" onerror="alert(1)">\n\n![Mô tả ảnh](https://example.com/tracker.png)\n\n`<script>not executable</script>`');
    expect(container.querySelector("script, img, iframe")).toBeNull();
    expect(screen.getByText("Mô tả ảnh")).toBeVisible();
    expect(screen.getByText("<script>not executable</script>").tagName).toBe("CODE");
  });

  it("rejects dangerous link protocols and isolates allowed links from the opener", () => {
    renderAnswer("[Tài liệu](https://example.com/policy) và [Email](mailto:shop@example.com) và [Không an toàn](javascript:alert%281%29) và [Dữ liệu](data:text/html,test)");
    const safeLink = screen.getByRole("link", { name: "Tài liệu" });
    expect(safeLink).toHaveAttribute("href", "https://example.com/policy");
    expect(safeLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(safeLink).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "Email" })).toHaveAttribute("href", "mailto:shop@example.com");
    expect(screen.queryByRole("link", { name: "Không an toàn" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dữ liệu" })).not.toBeInTheDocument();
    expect(screen.getByText("Không an toàn")).toBeVisible();
  });

  it("does not parse user messages or error messages as Markdown", () => {
    const text = "**Nguyên văn** <img src=x>\n- Không phải danh sách";
    const { container } = render(<>
      <ChatMessage entry={{ id: "user", role: "user", text }} />
      <ChatMessage entry={{ id: "error", role: "error", text }} />
    </>);
    expect(container.querySelector(".message--user .message-text")?.textContent).toBe(text);
    expect(container.querySelector(".message--error .message-text")?.textContent).toBe(text);
    expect(container.querySelector(".assistant-content, img, ul")).toBeNull();
  });
});

describe("Compact model selector", () => {
  it("keeps the full model name accessible and unconfigured models disabled", () => {
    render(<ModelSelector disabled={false} selectedModel="inetcloud-knowledge" onSelect={vi.fn()} models={[
      { id: "inetcloud-knowledge", label: "iNetCloud Knowledge", provider: "inetcloud", configured: true },
      { id: "gemini", label: "Gemini", provider: "gemini", configured: false },
    ]} />);
    expect(screen.getByRole("combobox", { name: "Chọn mô hình AI" })).toHaveAttribute("title", "iNetCloud Knowledge");
    expect(screen.getByRole("option", { name: "iNetCloud Knowledge" })).toHaveTextContent("Knowledge");
    expect(screen.getByRole("option", { name: "Gemini · Chưa cấu hình" })).toBeDisabled();
  });
});
