import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type {
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  Dataset,
} from "./types";

const conversationId = "11111111-1111-4111-8111-111111111111";
const secondConversationId = "22222222-2222-4222-8222-222222222222";
const defaultDataset: Dataset = {
  dataset_id: null,
  kind: "default",
  name: "Dữ liệu cửa hàng mẫu",
  original_filename: null,
  file_type: null,
  sheet_name: null,
  row_count: null,
  column_count: null,
  columns: [],
  created_at: null,
};
const uploadedDataset: Dataset = {
  dataset_id: 7,
  kind: "uploaded",
  name: "Doanh số 2026",
  original_filename: "sales.csv",
  file_type: "csv",
  sheet_name: null,
  row_count: 2,
  column_count: 2,
  columns: [
    { source_name: "Sản phẩm", name: "san_pham", data_type: "TEXT" },
    { source_name: "Doanh thu", name: "doanh_thu", data_type: "BIGINT" },
  ],
  created_at: "2026-10-14T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
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

function summary(id = conversationId, overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    conversation_id: id,
    title: "Cuộc trò chuyện mới",
    dataset_id: null,
    dataset_name: "Dữ liệu cửa hàng mẫu",
    created_at: "2026-10-14T00:00:00Z",
    updated_at: "2026-10-14T00:00:00Z",
    ...overrides,
  };
}

interface MockOptions {
  response?: ChatResponse;
  conversations?: ConversationSummary[];
  details?: Record<string, ConversationDetail>;
  datasets?: Dataset[];
  delayMessage?: boolean;
  delayBootstrap?: boolean;
}

function installApi(options: MockOptions = {}) {
  const conversations = options.conversations ?? [];
  const datasets = options.datasets ?? [defaultDataset];
  const response = options.response ?? chatResponse();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawUrl = typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input?.url ?? "http://localhost/__aborted_request__";
    const url = new URL(rawUrl, "http://localhost");
    const method = init?.method ?? "GET";
    if (url.pathname === "/api/health") return jsonResponse({ status: "ok", service: "ShopQuery AI" });
    if (url.pathname === "/api/datasets" && method === "GET") return jsonResponse(datasets);
    if (url.pathname === "/api/conversations" && method === "GET") {
      if (options.delayBootstrap) await new Promise((resolve) => setTimeout(resolve, 80));
      return jsonResponse(conversations);
    }
    if (url.pathname === "/api/conversations" && method === "POST") return jsonResponse(summary(), 201);
    if (url.pathname === `/api/conversations/${conversationId}` && method === "GET") {
      return jsonResponse(options.details?.[conversationId] ?? { ...summary(), messages: [] });
    }
    if (url.pathname === `/api/conversations/${secondConversationId}` && method === "GET") {
      return jsonResponse(options.details?.[secondConversationId] ?? { ...summary(secondConversationId), messages: [] });
    }
    if (url.pathname.endsWith("/messages") && method === "POST") {
      if (options.delayMessage) await new Promise((resolve) => setTimeout(resolve, 80));
      return jsonResponse({
        conversation: summary(conversationId, { title: "Top sản phẩm" }),
        user_message: { message_id: 1, role: "user", content: "Top sản phẩm", response: null, created_at: "2026-10-14T00:00:01Z" },
        assistant_message: { message_id: 2, role: response.error ? "error" : "assistant", content: response.answer, response, created_at: "2026-10-14T00:00:02Z" },
      });
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "PATCH") {
      return jsonResponse(summary(conversationId, { title: "Tên đã đổi" }));
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "DELETE") return jsonResponse(null, 204);
    if (url.pathname === "/api/datasets/preview" && method === "POST") {
      return jsonResponse({
        filename: "sales.csv",
        file_type: "csv",
        sheet_name: null,
        sheet_names: [],
        row_count: 2,
        column_count: 2,
        columns: uploadedDataset.columns,
        rows: [{ "Sản phẩm": "Áo", "Doanh thu": "120000" }],
        warnings: [],
      });
    }
    if (url.pathname === "/api/datasets/import" && method === "POST") return jsonResponse(uploadedDataset, 201);
    return jsonResponse({ detail: "not mocked" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => installApi());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ShopQuery workspace", () => {
  it("hiển thị sidebar, dữ liệu mặc định, trạng thái API và empty state", async () => {
    render(<App />);

    expect(await screen.findByText("API sẵn sàng")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đoạn chat mới" })).toBeInTheDocument();
    expect(screen.getAllByText("Dữ liệu cửa hàng mẫu").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Bạn muốn khám phá điều gì?" })).toBeInTheDocument();
  });

  it("chặn câu hỏi trống và dài hơn 2000 ký tự", async () => {
    render(<App />);
    const input = await screen.findByLabelText("Nhập câu hỏi cho ShopQuery AI");

    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("Vui lòng nhập câu hỏi.")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "a".repeat(2_001) } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("Câu hỏi không được vượt quá 2000 ký tự.")).toBeInTheDocument();
  });

  it("tạo conversation, gửi một lần và hiển thị SQL cùng bảng", async () => {
    const fetchMock = installApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /Phân tích bán hàng/ }));

    expect(await screen.findByText("Đây là câu trả lời.")).toBeInTheDocument();
    expect(screen.getByText("SQL")).toBeInTheDocument();
    expect(screen.getByText("Xem câu lệnh SQL")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toHaveTextContent("Áo linen");
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/messages"))).toHaveLength(1);
  });

  it("khôi phục đúng lịch sử conversation sau khi tải trang", async () => {
    const existing = summary(conversationId, { title: "Doanh thu tháng 9" });
    installApi({
      conversations: [existing],
      details: {
        [conversationId]: {
          ...existing,
          messages: [
            { message_id: 10, role: "user", content: "Doanh thu?", response: null, created_at: "2026-10-14T00:00:01Z" },
            { message_id: 11, role: "assistant", content: "120 triệu đồng.", response: chatResponse({ answer: "120 triệu đồng." }), created_at: "2026-10-14T00:00:02Z" },
          ],
        },
      },
    });

    render(<App />);

    expect(await screen.findByText("120 triệu đồng.")).toBeInTheDocument();
    expect(screen.getAllByText("Doanh thu tháng 9").length).toBeGreaterThan(0);
  });

  it("đổi tên và xóa conversation qua menu", async () => {
    const existing = summary();
    installApi({ conversations: [existing], details: { [conversationId]: { ...existing, messages: [] } } });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: `Tùy chọn cho ${existing.title}` });

    await user.click(screen.getByRole("button", { name: `Tùy chọn cho ${existing.title}` }));
    await user.click(screen.getByRole("menuitem", { name: /Đổi tên/ }));
    const titleInput = screen.getByLabelText("Tên cuộc trò chuyện");
    await user.clear(titleInput);
    await user.type(titleInput, "Tên đã đổi");
    await user.click(screen.getByRole("button", { name: "Lưu tên" }));
    expect((await screen.findAllByText("Tên đã đổi")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Tùy chọn cho Tên đã đổi" }));
    await user.click(screen.getByRole("menuitem", { name: /Xóa/ }));
    await user.click(screen.getByRole("button", { name: "Xóa cuộc trò chuyện" }));
    await waitFor(() => expect(screen.queryByText("Tên đã đổi")).not.toBeInTheDocument());
  });

  it("yêu cầu xác nhận trước khi đổi dataset của conversation", async () => {
    const existing = summary();
    installApi({
      conversations: [existing],
      details: { [conversationId]: { ...existing, messages: [{ message_id: 1, role: "user", content: "Câu hỏi cũ", response: null, created_at: "2026-10-14T00:00:00Z" }] } },
      datasets: [defaultDataset, uploadedDataset],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Câu hỏi cũ");

    await user.click(screen.getByRole("button", { name: /Doanh số 2026/ }));
    expect(screen.getByRole("dialog", { name: "Chuyển bộ dữ liệu?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bắt đầu chat mới" }));
    expect(await screen.findByText(/Đang sử dụng/)).toHaveTextContent("Doanh số 2026");
    expect(screen.queryByText("Câu hỏi cũ")).not.toBeInTheDocument();
  });

  it("preview và xác nhận import CSV", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("API sẵn sàng");
    await user.click(screen.getByRole("button", { name: "Nạp dữ liệu mới" }));

    const file = new File(["Sản phẩm,Doanh thu\nÁo,120000\n"], "sales.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/Chọn file CSV hoặc XLSX/), file);

    expect(await screen.findByText("120000")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "2 dòng")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Xác nhận import" }));
    expect(await screen.findByText(/Đang sử dụng/)).toHaveTextContent("Doanh số 2026");
    expect(screen.getByLabelText("Thông tin bộ dữ liệu đang dùng")).toHaveTextContent("sales.csv");
    expect(screen.getByLabelText("Thông tin bộ dữ liệu đang dùng")).toHaveTextContent("Sản phẩm: TEXT");
  });

  it("hiển thị RAG, Hybrid và Unsupported mà không tạo evidence giả", async () => {
    const user = userEvent.setup();
    installApi({ response: chatResponse({ route: "RAG", sql: null, rows: [], sources: [{ chunk_id: 7, source_file: "return.md", section_title: "Đổi trả", content: "Đổi trả trong 14 ngày." }] }) });
    const first = render(<App />);
    await user.click(await screen.findByRole("button", { name: /Tra cứu chính sách/ }));
    expect(await screen.findByText("Nguồn tham khảo · 1")).toBeInTheDocument();
    first.unmount();

    installApi({ response: chatResponse({ route: "HYBRID", sources: [{ chunk_id: 9, source_file: "shipping.md", section_title: "Vận chuyển", content: "Laptop miễn phí." }] }) });
    const second = render(<App />);
    await user.click(await screen.findByRole("button", { name: /Kết hợp dữ liệu/ }));
    expect(await screen.findByText("SQL + Tài liệu")).toBeInTheDocument();
    second.unmount();

    installApi({ response: chatResponse({ route: "UNSUPPORTED", sql: null, rows: [], sources: [] }) });
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /Phân tích bán hàng/ }));
    expect(await screen.findByText("Ngoài phạm vi")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Kết quả truy vấn" })).not.toBeInTheDocument();
  });

  it("không đưa response của conversation cũ vào conversation mới", async () => {
    installApi({ delayMessage: true });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("API sẵn sàng");
    const input = screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI");
    await user.type(input, "Top sản phẩm");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    await user.click(screen.getByRole("button", { name: "Đoạn chat mới" }));

    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(screen.queryByText("Đây là câu trả lời.")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bạn muốn khám phá điều gì?" })).toBeInTheDocument();
  });

  it("không khôi phục conversation cũ sau khi người dùng đã chọn chat mới", async () => {
    const existing = summary(conversationId, { title: "Lịch sử cũ" });
    installApi({
      conversations: [existing],
      delayBootstrap: true,
      details: {
        [conversationId]: {
          ...existing,
          messages: [
            { message_id: 1, role: "user", content: "Nội dung cũ", response: null, created_at: "2026-10-14T00:00:00Z" },
          ],
        },
      },
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Đoạn chat mới" }));
    await new Promise((resolve) => setTimeout(resolve, 120));

    expect(screen.queryByText("Nội dung cũ")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bạn muốn khám phá điều gì?" })).toBeInTheDocument();
  });
});
