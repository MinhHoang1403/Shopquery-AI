import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  previewError?: string;
  importError?: string;
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
      if (options.previewError) return jsonResponse({ detail: options.previewError }, 422);
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
    if (url.pathname === "/api/datasets/import" && method === "POST") {
      if (options.importError) return jsonResponse({ detail: options.importError }, 409);
      return jsonResponse(uploadedDataset, 201);
    }
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
  it("hiển thị sidebar tối giản, dataset selector và empty state", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("API sẵn sàng")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đoạn chat mới" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Dữ liệu" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chọn bộ dữ liệu.*Dữ liệu cửa hàng mẫu/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeInTheDocument();
    expect(screen.getByText("Khám phá dữ liệu, phân tích kinh doanh và tra cứu thông tin bằng AI.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Thu gọn sidebar" }));
    expect(screen.getByRole("button", { name: "Mở rộng sidebar" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mở rộng sidebar" }));
    expect(screen.getByRole("button", { name: "Thu gọn sidebar" })).toBeInTheDocument();
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

  it("giữ Shift+Enter để xuống dòng và Enter để gửi", async () => {
    const fetchMock = installApi();
    const user = userEvent.setup();
    render(<App />);
    const input = await screen.findByLabelText("Nhập câu hỏi cho ShopQuery AI");

    await user.type(input, "Dòng một{Shift>}{Enter}{/Shift}Dòng hai");
    expect(input).toHaveValue("Dòng một\nDòng hai");
    expect(screen.getByText("17/2000")).toBeInTheDocument();

    await user.type(input, "{Enter}");
    expect(await screen.findByText("Đây là câu trả lời.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/messages"))).toHaveLength(1);
  });

  it("giữ SQL và bảng đóng mặc định, chỉ mở một panel và sao chép SQL", async () => {
    const fetchMock = installApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /Phân tích bán hàng/ }));

    expect(await screen.findByText("Đây là câu trả lời.")).toBeInTheDocument();
    expect(screen.getByText("SQL")).toBeInTheDocument();
    const sqlControl = screen.getByRole("button", { name: "Xem SQL" });
    const tableControl = screen.getByRole("button", { name: "Bảng dữ liệu · 1" });
    expect(sqlControl).toHaveAttribute("aria-expanded", "false");
    expect(tableControl).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/SELECT name, quantity/)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Kết quả truy vấn" })).not.toBeInTheDocument();

    await user.click(tableControl);
    expect(tableControl).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toHaveTextContent("Áo linen");

    await user.click(sqlControl);
    expect(tableControl).toHaveAttribute("aria-expanded", "false");
    expect(sqlControl).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("region", { name: "Kết quả truy vấn" })).not.toBeInTheDocument();
    expect(screen.getByText(/SELECT name, quantity/)).toBeVisible();
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: "Sao chép SQL" }));
    expect(clipboardWrite).toHaveBeenCalledWith("SELECT name, quantity FROM products ORDER BY quantity DESC LIMIT 5");
    await user.click(sqlControl);
    expect(sqlControl).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/SELECT name, quantity/)).not.toBeInTheDocument();
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
            { message_id: 12, role: "user", content: "Sản phẩm nào nổi bật?", response: null, created_at: "2026-10-14T00:00:03Z" },
            { message_id: 13, role: "assistant", content: "Áo linen nổi bật.", response: chatResponse({ answer: "Áo linen nổi bật." }), created_at: "2026-10-14T00:00:04Z" },
          ],
        },
      },
    });

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("120 triệu đồng.")).toBeInTheDocument();
    expect(screen.getAllByText("Doanh thu tháng 9").length).toBeGreaterThan(0);
    const tableControls = screen.getAllByRole("button", { name: "Bảng dữ liệu · 1" });
    expect(tableControls).toHaveLength(2);
    expect(tableControls[0]).toHaveAttribute("aria-expanded", "false");
    expect(tableControls[1]).toHaveAttribute("aria-expanded", "false");
    await user.click(tableControls[0]);
    expect(tableControls[0]).toHaveAttribute("aria-expanded", "true");
    expect(tableControls[1]).toHaveAttribute("aria-expanded", "false");
    await user.click(tableControls[1]);
    expect(tableControls[0]).toHaveAttribute("aria-expanded", "true");
    expect(tableControls[1]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("region", { name: "Kết quả truy vấn" })).toHaveLength(2);
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

    await user.click(screen.getByRole("button", { name: /Chọn bộ dữ liệu/ }));
    await user.click(screen.getByRole("menuitemradio", { name: /Doanh số 2026/ }));
    expect(screen.getByRole("dialog", { name: "Chuyển bộ dữ liệu?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bắt đầu chat mới" }));
    expect(screen.getByRole("button", { name: /Chọn bộ dữ liệu.*Doanh số 2026/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kiểm tra dữ liệu/ })).toBeInTheDocument();
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
    expect(await screen.findByText("Đã import Doanh số 2026 thành công.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Chọn bộ dữ liệu.*Doanh số 2026/ }));
    await user.click(screen.getByText("Xem thông tin dữ liệu"));
    expect(screen.getByText("sales.csv")).toBeInTheDocument();
    expect(screen.getByText(/Sản phẩm: TEXT/)).toBeInTheDocument();
  });

  it("hiển thị lỗi 422 khi file tải lên không hợp lệ", async () => {
    installApi({ previewError: "File vượt quá giới hạn 10 MB." });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Nạp dữ liệu mới" }));

    const file = new File(["invalid"], "sales.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/Chọn file CSV hoặc XLSX/), file);

    const dialog = screen.getByRole("dialog", { name: "Nạp dữ liệu mới" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("File vượt quá giới hạn 10 MB.");
    expect(screen.getByRole("button", { name: "Xác nhận import" })).toBeDisabled();
  });

  it("giữ hộp thoại và báo lỗi 409 khi tên bộ dữ liệu bị trùng", async () => {
    installApi({ importError: "Tên bộ dữ liệu đã tồn tại." });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Nạp dữ liệu mới" }));

    const file = new File(["Sản phẩm,Doanh thu\nÁo,120000\n"], "sales.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/Chọn file CSV hoặc XLSX/), file);
    await user.click(await screen.findByRole("button", { name: "Xác nhận import" }));

    const dialog = screen.getByRole("dialog", { name: "Nạp dữ liệu mới" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Tên bộ dữ liệu đã tồn tại.");
    expect(dialog).toBeInTheDocument();
    expect(screen.queryByText(/Đã import .* thành công/)).not.toBeInTheDocument();
  });

  it("hiển thị toolbar đúng theo RAG, Hybrid và response không có evidence", async () => {
    const user = userEvent.setup();
    installApi({ response: chatResponse({ route: "RAG", sql: null, rows: [], sources: [{ chunk_id: 7, source_file: "return.md", section_title: "Đổi trả", content: "Đổi trả trong 14 ngày." }] }) });
    const first = render(<App />);
    await user.click(await screen.findByRole("button", { name: /Tra cứu chính sách/ }));
    const ragSources = await screen.findByRole("button", { name: "Nguồn · 1" });
    expect(ragSources).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("return.md")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bảng dữ liệu/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xem SQL" })).not.toBeInTheDocument();
    await user.click(ragSources);
    expect(screen.getByText("return.md")).toBeVisible();
    expect(screen.getByText("Đổi trả")).toBeVisible();
    expect(screen.getByText("Đổi trả trong 14 ngày.")).not.toBeVisible();
    await user.click(screen.getByText("Đổi trả"));
    expect(screen.getByText("Đổi trả trong 14 ngày.")).toBeVisible();
    first.unmount();

    installApi({ response: chatResponse({ route: "HYBRID", sources: [{ chunk_id: 9, source_file: "shipping.md", section_title: "Vận chuyển", content: "Laptop miễn phí." }] }) });
    const second = render(<App />);
    await user.click(await screen.findByRole("button", { name: /Kết hợp dữ liệu/ }));
    expect(await screen.findByText("SQL + Tài liệu")).toBeInTheDocument();
    const hybridRows = screen.getByRole("button", { name: "Bảng dữ liệu · 1" });
    const hybridSql = screen.getByRole("button", { name: "Xem SQL" });
    const hybridSources = screen.getByRole("button", { name: "Nguồn · 1" });
    expect(hybridRows).toHaveAttribute("aria-expanded", "false");
    expect(hybridSql).toHaveAttribute("aria-expanded", "false");
    expect(hybridSources).toHaveAttribute("aria-expanded", "false");
    await user.click(hybridRows);
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();
    await user.click(hybridSql);
    expect(screen.queryByRole("region", { name: "Kết quả truy vấn" })).not.toBeInTheDocument();
    expect(screen.getByText(/SELECT name, quantity/)).toBeVisible();
    await user.click(hybridSources);
    expect(screen.queryByText(/SELECT name, quantity/)).not.toBeInTheDocument();
    expect(screen.getByText("shipping.md")).toBeVisible();
    await user.click(hybridSources);
    expect(screen.queryByText("shipping.md")).not.toBeInTheDocument();
    second.unmount();

    installApi({ response: chatResponse({ route: "UNSUPPORTED", sql: null, rows: [], sources: [] }) });
    const third = render(<App />);
    await user.click(await screen.findByRole("button", { name: /Phân tích bán hàng/ }));
    expect(await screen.findByText("Ngoài phạm vi")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Bằng chứng hỗ trợ" })).not.toBeInTheDocument();
    third.unmount();

    installApi({ response: chatResponse({ sql: null, rows: [], sources: [] }) });
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /Phân tích bán hàng/ }));
    expect(await screen.findByText("Đây là câu trả lời.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Bằng chứng hỗ trợ" })).not.toBeInTheDocument();
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
    expect(screen.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeInTheDocument();
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
    expect(screen.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeInTheDocument();
  });
});
