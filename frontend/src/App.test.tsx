import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ChatResponse } from "./types";

const healthResponse = { status: "ok", service: "ShopQuery AI" };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function chatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    answer: "Đây là câu trả lời.",
    route: "SQL",
    sql: "SELECT name, quantity FROM products ORDER BY quantity DESC LIMIT 5",
    rows: [{ name: "Áo linen", quantity: 42 }],
    sources: [],
    error: null,
    ...overrides,
  };
}

function mockHealthAndChat(response: Response | Promise<Response>) {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(healthResponse))
    .mockImplementationOnce(() => response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(healthResponse)));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ShopQuery chat", () => {
  it("hiển thị giao diện khởi đầu và trạng thái API", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /Tìm câu trả lời/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Phân tích bán hàng|Tra cứu chính sách|Kết hợp dữ liệu/ })).toHaveLength(3);
    expect(await screen.findByText("API sẵn sàng")).toBeInTheDocument();
  });

  it("chặn câu hỏi trống và câu hỏi dài hơn 2000 ký tự", async () => {
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI");

    await user.type(input, "   ");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("Vui lòng nhập câu hỏi.")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "a".repeat(2_001) } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("Câu hỏi không được vượt quá 2000 ký tự.")).toBeInTheDocument();
  });

  it("hiển thị nhánh SQL với truy vấn và bảng động", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse())));
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Phân tích bán hàng/ }));

    expect(await screen.findByText("Đây là câu trả lời.")).toBeInTheDocument();
    expect(screen.getByText("Dữ liệu SQL")).toBeInTheDocument();
    expect(screen.getByText("Câu lệnh SQL")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toHaveTextContent("Áo linen");
  });

  it("hiển thị nhánh RAG với nguồn tài liệu", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse({
      answer: "Đổi trả trong 30 ngày.",
      route: "RAG",
      sql: null,
      rows: [],
      sources: [{
        chunk_id: 7,
        source_file: "return-policy.md",
        section_title: "Thời hạn đổi trả",
        content: "Khách hàng được đổi trả trong vòng 30 ngày.",
      }],
    }))));
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Chính sách đổi trả/ }));

    expect(await screen.findByText("Đổi trả trong 30 ngày.")).toBeInTheDocument();
    expect(screen.getByText("Tài liệu")).toBeInTheDocument();
    expect(screen.getByText("Thời hạn đổi trả")).toBeInTheDocument();
    expect(screen.getByText("return-policy.md")).toBeInTheDocument();
    expect(screen.queryByText("Câu lệnh SQL")).not.toBeInTheDocument();
  });

  it("hiển thị nhánh Hybrid với cả bảng và nguồn", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse({
      answer: "Ba sản phẩm thuộc diện miễn phí vận chuyển.",
      route: "HYBRID",
      sources: [{
        chunk_id: 9,
        source_file: "shipping-policy.md",
        section_title: "Miễn phí vận chuyển",
        content: "Một số danh mục được miễn phí vận chuyển.",
      }],
    }))));
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /miễn phí vận chuyển/ }));

    expect(await screen.findByText("Ba sản phẩm thuộc diện miễn phí vận chuyển.")).toBeInTheDocument();
    expect(screen.getByText("SQL + Tài liệu")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toBeInTheDocument();
    expect(screen.getByText("Miễn phí vận chuyển")).toBeInTheDocument();
  });

  it("không dựng vùng bằng chứng rỗng cho câu hỏi ngoài phạm vi", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse({
      answer: "Câu hỏi nằm ngoài phạm vi dữ liệu cửa hàng.",
      route: "UNSUPPORTED",
      sql: null,
      rows: [],
      sources: [],
    }))));
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI");

    await user.type(input, "Hôm nay thời tiết thế nào?");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));

    expect(await screen.findByText("Câu hỏi nằm ngoài phạm vi dữ liệu cửa hàng.")).toBeInTheDocument();
    expect(screen.getByText("Ngoài phạm vi")).toBeInTheDocument();
    expect(screen.queryByText("Nguồn tham khảo")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("coi HTTP 200 có error là thất bại và giữ lại câu hỏi", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse({
      answer: "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
      route: null,
      sql: null,
      rows: [],
      sources: [],
      error: "gemini_unavailable",
    }))));
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Chính sách đổi trả/ }));

    expect(await screen.findByText("Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.")).toBeInTheDocument();
    expect(screen.getByText("Không thể xử lý")).toBeInTheDocument();
    expect(screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI")).toHaveValue("Chính sách đổi trả của cửa hàng như thế nào?");
  });

  it("hiển thị lỗi mạng, lỗi 422 và phản hồi sai định dạng", async () => {
    const cases: Array<[() => Response | Promise<Response>, string]> = [
      [() => Promise.reject(new TypeError("offline")), "Không thể kết nối đến máy chủ"],
      [() => jsonResponse({ detail: [] }, 422), "Câu hỏi không hợp lệ"],
      [() => jsonResponse({ answer: "thiếu trường" }), "Phản hồi từ máy chủ không đúng định dạng"],
    ];

    for (const [createResponse, expected] of cases) {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(jsonResponse(healthResponse))
        .mockImplementationOnce(() => createResponse());
      vi.stubGlobal("fetch", fetchMock);
      const { unmount } = render(<App />);
      const input = screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI");
      fireEvent.change(input, { target: { value: "Một câu hỏi hợp lệ" } });
      fireEvent.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
      expect(await screen.findByText(new RegExp(expected))).toBeInTheDocument();
      unmount();
    }
  });

  it("không gửi yêu cầu trùng khi đang tải", async () => {
    let resolveChat!: (response: Response) => void;
    const pendingChat = new Promise<Response>((resolve) => { resolveChat = resolve; });
    const fetchMock = mockHealthAndChat(pendingChat);
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI");

    await user.type(input, "Doanh số tháng này?");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    expect(input).toBeDisabled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    resolveChat(jsonResponse(chatResponse()));
    expect(await screen.findByText("Đây là câu trả lời.")).toBeInTheDocument();
  });

  it("thông báo rõ khi SQL không có dòng và RAG không có nguồn", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse({ rows: [] }))));
    const user = userEvent.setup();
    const first = render(<App />);
    await user.click(screen.getByRole("button", { name: /Phân tích bán hàng/ }));
    expect(await screen.findByText("Truy vấn không trả về bản ghi nào.")).toBeInTheDocument();
    first.unmount();

    mockHealthAndChat(Promise.resolve(jsonResponse(chatResponse({
      route: "RAG", sql: null, rows: [], sources: [],
    }))));
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Chính sách đổi trả/ }));
    expect(await screen.findByText("Không có nguồn tài liệu phù hợp.")).toBeInTheDocument();
  });

  it("hiển thị lỗi máy chủ cho HTTP 500", async () => {
    mockHealthAndChat(Promise.resolve(jsonResponse({ error: "internal_error" }, 500)));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Chính sách đổi trả/ }));
    await waitFor(() => expect(screen.getByText(/Máy chủ gặp sự cố/)).toBeInTheDocument());
  });
});
