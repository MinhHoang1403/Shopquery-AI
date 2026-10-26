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
  table_count: 1,
  document_count: 0,
  tables: [{
    dataset_table_id: 12,
    display_name: "sales",
    original_filename: "sales.csv",
    file_type: "csv",
    sheet_name: null,
    row_count: 2,
    column_count: 2,
    columns: [
      { source_name: "Sản phẩm", name: "san_pham", data_type: "TEXT" },
      { source_name: "Doanh thu", name: "doanh_thu", data_type: "BIGINT" },
    ],
  }],
  created_at: "2026-10-14T00:00:00Z",
};
const emptyWorkspace: Dataset = {
  ...uploadedDataset,
  name: "Doanh số 2026",
  original_filename: null,
  file_type: null,
  row_count: null,
  column_count: null,
  columns: [],
  table_count: 0,
  tables: [],
};

it("shows a clean workspace without demo prompts or chat requests when there is no data", async () => {
  const fetch = installApi({ datasets: [] });
  render(<App />);
  await screen.findByRole("heading", { name: "Không gian dữ liệu của bạn" });
  expect(screen.getByText("Chưa có bộ dữ liệu")).toBeInTheDocument();
  expect(screen.queryByText("Phân tích bán hàng")).not.toBeInTheDocument();
  const input = screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI");
  expect(input).toBeEnabled();
  fireEvent.change(input, { target: { value: "Tổng học phí?" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(await screen.findByRole("alert")).toHaveTextContent("Hãy tải dữ liệu lên");
  expect(input).toHaveValue("Tổng học phí?");
  expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Thêm dữ liệu" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("keeps the composer editable and explains provider denial without creating a chat", async () => {
  const fetch = installApi({ aiEnabled: false });
  render(<App />);
  const input = await screen.findByLabelText("Nhập câu hỏi cho ShopQuery AI");
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: "Tổng học phí?" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("chưa cho phép");
  expect(input).toHaveValue("Tổng học phí?");
  expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(0);
});

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
  aiEnabled?: boolean;
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
    if (url.pathname === "/api/uploads/limits") return jsonResponse({ max_file_bytes: 10485760, max_rows: 5000, max_columns: 30, max_pdf_pages: 100, provider_data_enabled: false, preview_per_hour: 180, upload_per_hour: 60 });
    if (url.pathname === "/api/models") return jsonResponse({
      ai_enabled: options.aiEnabled ?? true,
      default_model: "inetcloud-knowledge",
      gemini_fallback_enabled: false,
      models: [
        { id: "inetcloud-knowledge", label: "iNetCloud Knowledge", provider: "inetcloud", configured: true },
        { id: "gemini", label: "Gemini", provider: "gemini", configured: true },
      ],
    });
    if (url.pathname === "/api/health") return jsonResponse({ status: "ok", service: "ShopQuery AI" });
    if (url.pathname === "/api/datasets" && method === "GET") return jsonResponse(datasets);
    if (url.pathname === "/api/datasets" && method === "POST") {
      if (options.importError) return jsonResponse({ detail: options.importError }, 409);
      return jsonResponse(emptyWorkspace, 201);
    }
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
    if (
      (url.pathname === "/api/datasets/preview" ||
        url.pathname === "/api/datasets/7/tables/preview") &&
      method === "POST"
    ) {
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
    if (url.pathname === "/api/datasets/7/documents" && method === "GET") {
      return jsonResponse([]);
    }
    if (url.pathname === "/api/datasets/7" && method === "GET") {
      return jsonResponse(datasets.find((item) => item.dataset_id === 7) ?? uploadedDataset);
    }
    if (url.pathname === "/api/datasets/7" && method === "DELETE") {
      return jsonResponse(null, 204);
    }
    if (url.pathname === "/api/datasets/7/tables/import" && method === "POST") {
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
  it.each([false, true])("upload updates workspace safely; same conversation workspace=%s", async (sameWorkspace) => {
    const existing = summary(conversationId, { title: "Lịch sử đã lưu", dataset_id: sameWorkspace ? 7 : null, dataset_name: sameWorkspace ? uploadedDataset.name : defaultDataset.name });
    const fetch = installApi({ conversations: [existing], datasets: [defaultDataset, uploadedDataset], details: {
      [conversationId]: { ...existing, messages: [{ message_id: 1, role: "user", content: "Câu hỏi giữ trong lịch sử", response: null, created_at: "2026-10-14T00:00:00Z" }] },
    } });
    const user = userEvent.setup(); render(<App />);
    await screen.findByText("Câu hỏi giữ trong lịch sử");
    await user.click(screen.getByRole("button", { name: "Quản lý dữ liệu" }));
    if (!sameWorkspace) await user.click(screen.getByRole("tab", { name: "Quản lý bộ hiện có" }));
    const file = new File(["Sản phẩm,Doanh thu\nÁo,120000\n"], "sales.csv", { type: "text/csv" });
    await user.upload(await screen.findByLabelText(/Thêm CSV hoặc XLSX/), file);
    await screen.findByText("120000");
    await user.click(screen.getByRole("button", { name: "Thêm bảng" }));
    await screen.findByText("Đã cập nhật Doanh số 2026 thành công.");
    await user.click(screen.getByRole("button", { name: "Trò chuyện với dữ liệu" }));
    expect(screen.getByRole("button", { name: /Chọn bộ dữ liệu.*Doanh số 2026/ })).toBeInTheDocument();
    if (sameWorkspace) expect(screen.getByText("Câu hỏi giữ trong lịch sử")).toBeInTheDocument();
    else expect(screen.queryByText("Câu hỏi giữ trong lịch sử")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lịch sử đã lưu" })).toBeInTheDocument();
    expect(screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI")).toBeEnabled();
    expect(fetch.mock.calls.some(([url, options]) => String(url).endsWith("/messages") && options?.method === "POST")).toBe(false);
    expect(fetch.mock.calls.some(([, options]) => options?.method === "DELETE" || options?.method === "PATCH")).toBe(false);
  });
  it("uses Auto Routing without asking the user to select a source", async () => {
    const fetch = installApi();
    render(<App />);
    const input = await screen.findByLabelText("Nhập câu hỏi cho ShopQuery AI");
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.queryByRole("combobox", { name: "Nguồn trả lời" })).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: "Tổng số bản ghi?" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    await screen.findByText("Đây là câu trả lời.");
    const send = fetch.mock.calls.find(([url, options]) => String(url).endsWith("/messages") && options?.method === "POST");
    expect(JSON.parse(String(send?.[1]?.body))).toMatchObject({ message: "Tổng số bản ghi?" });
    expect(JSON.parse(String(send?.[1]?.body))).not.toHaveProperty("route_hint");
  });
  it("xóa workspace đang mở sẽ bỏ chat liên quan và trở về dữ liệu mẫu", async () => {
    const existing = summary(conversationId, {
      title: "Chat học phí cần xóa", dataset_id: 7, dataset_name: uploadedDataset.name,
    });
    const unrelated = summary(secondConversationId, { title: "Chat cửa hàng cần giữ" });
    const fetchMock = installApi({
      datasets: [defaultDataset, uploadedDataset], conversations: [existing, unrelated],
      details: { [conversationId]: { ...existing, messages: [{
        message_id: 1, role: "user", content: "Nội dung của workspace bị xóa",
        response: null, created_at: "2026-10-19T00:00:00Z",
      }] } },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Nội dung của workspace bị xóa");
    await user.click(screen.getByRole("button", { name: "Quản lý dữ liệu" }));
    await user.click(screen.getByRole("tab", { name: "Quản lý bộ hiện có" }));
    await user.click(await screen.findByRole("button", { name: "Xóa bộ dữ liệu" }));
    await user.click(screen.getByRole("checkbox", { name: /Xóa cả lịch sử chat/ }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    await screen.findByText(/Đã xóa Doanh số 2026/);
    expect(fetchMock).toHaveBeenCalledWith("/api/datasets/7?delete_conversations=true", expect.objectContaining({ method: "DELETE", credentials: "same-origin" }));
    expect(screen.queryByText("Nội dung của workspace bị xóa")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Chat học phí cần xóa" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chat cửa hàng cần giữ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chọn bộ dữ liệu.*Dữ liệu cửa hàng mẫu/ })).toBeInTheDocument();
  });

  it("hiển thị lý do provider thất bại và không gán model cho đáp án không tồn tại", async () => {
    installApi({ response: chatResponse({
      answer: "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.", route: null,
      sql: null, rows: [], sources: [], error: "Knowledge tạm thời không khả dụng.",
      requested_model: "inetcloud-knowledge", used_model: null, fallback_used: false,
    }) });
    const user = userEvent.setup();
    render(<App />);
    const input = await screen.findByLabelText("Nhập câu hỏi cho ShopQuery AI");
    await waitFor(() => expect(input).not.toBeDisabled());
    await user.type(input, "Top sản phẩm{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Chưa thể hoàn tất truy vấn này.");
    await user.click(screen.getByRole("button", {name:"Chi tiết lỗi"}));
    expect(screen.getByText("Knowledge tạm thời không khả dụng.")).toBeVisible();
    expect(document.querySelector(".model-attribution")).not.toBeInTheDocument();
    expect(screen.queryByText(/Đã chuyển từ Knowledge sang Gemini/)).not.toBeInTheDocument();
  });

  it("gửi model đã chọn và không đổi attribution của câu trả lời khi đổi lựa chọn", async () => {
    const response = chatResponse({ requested_model: "gemini", used_model: "gemini", fallback_used: false });
    const fetchMock = installApi({ response });
    const user = userEvent.setup();
    render(<App />);
    const selector = await screen.findByLabelText("Chọn mô hình AI");
    await waitFor(() => expect(selector).not.toBeDisabled());
    expect(selector).toHaveValue("inetcloud-knowledge");
    await user.selectOptions(selector, "gemini");
    await user.type(screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI"), "Top sản phẩm{Enter}");
    await screen.findByText("Đây là câu trả lời.");
    const sent = fetchMock.mock.calls.find((call) => String(call[0]).endsWith("/messages"));
    expect(JSON.parse(String(sent?.[1]?.body)).model_id).toBe("gemini");
    expect(document.querySelector(".model-attribution")).toHaveTextContent("Gemini");
    await user.selectOptions(selector, "inetcloud-knowledge");
    expect(document.querySelector(".model-attribution")).toHaveTextContent("Gemini");
    const patch = fetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body)).model_id).toBe("inetcloud-knowledge");
  });

  it("khôi phục model preference và hiển thị thông báo fallback từ metadata", async () => {
    const response = chatResponse({ requested_model: "inetcloud-knowledge", used_model: "gemini", fallback_used: true });
    installApi({
      conversations: [summary()],
      details: { [conversationId]: { ...summary(), model_id: "gemini", messages: [
        { message_id: 2, role: "assistant", content: response.answer, response, created_at: "2026-10-18T00:00:00Z" },
      ] } },
    });
    render(<App />);
    await screen.findByText("Đây là câu trả lời.");
    expect(screen.getByLabelText("Chọn mô hình AI")).toHaveValue("gemini");
    expect(screen.getByText(/Đã chuyển từ Knowledge sang Gemini/)).toBeVisible();
  });

  it("khóa model selector khi đang gửi để request giữ đúng model", async () => {
    const fetchMock = installApi({ delayMessage: true });
    const user = userEvent.setup();
    render(<App />);
    const selector = await screen.findByLabelText("Chọn mô hình AI");
    await waitFor(() => expect(selector).not.toBeDisabled());
    await user.type(screen.getByLabelText("Nhập câu hỏi cho ShopQuery AI"), "Top sản phẩm");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    expect(selector).toBeDisabled();
    await screen.findByText("Đây là câu trả lời.");
    const sent = fetchMock.mock.calls.find((call) => String(call[0]).endsWith("/messages"));
    expect(JSON.parse(String(sent?.[1]?.body)).model_id).toBe("inetcloud-knowledge");
  });

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
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();

    await user.click(tableControl);
    expect(tableControl).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toHaveTextContent("Áo linen");

    await user.click(sqlControl);
    expect(tableControl).toHaveAttribute("aria-expanded", "false");
    expect(sqlControl).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();
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
    await user.click(screen.getByRole("button", { name: "Quản lý dữ liệu" }));

    await user.type(screen.getByLabelText("Tên bộ dữ liệu"), "Doanh số 2026");
    await user.click(screen.getByRole("button", { name: "Tạo workspace rỗng" }));

    const file = new File(["Sản phẩm,Doanh thu\nÁo,120000\n"], "sales.csv", { type: "text/csv" });
    await user.upload(await screen.findByLabelText(/Thêm CSV hoặc XLSX/), file);

    expect(await screen.findByText("120000")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Thêm bảng" }));
    expect(await screen.findByText("Đã cập nhật Doanh số 2026 thành công.")).toBeInTheDocument();
    await user.upload(screen.getByLabelText(/Thêm CSV hoặc XLSX/), file);
    expect(await screen.findByText("120000")).toBeInTheDocument();
    expect(screen.getByLabelText(/Thêm CSV hoặc XLSX/)).toHaveValue("");
    await user.click(screen.getAllByRole("button", { name: "Đóng" })[1]);
    await user.click(screen.getByRole("button", { name: /Chọn bộ dữ liệu.*Doanh số 2026/ }));
    expect(screen.getByText("1 bảng · 0 tài liệu")).toBeInTheDocument();
    await user.click(screen.getByText("Xem thông tin dữ liệu"));
  });

  it("hiển thị lỗi 422 khi file tải lên không hợp lệ", async () => {
    installApi({ previewError: "File vượt quá giới hạn 10 MB." });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Quản lý dữ liệu" }));

    await user.type(screen.getByLabelText("Tên bộ dữ liệu"), "Doanh số 2026");
    await user.click(screen.getByRole("button", { name: "Tạo workspace rỗng" }));

    const file = new File(["invalid"], "sales.csv", { type: "text/csv" });
    await user.upload(await screen.findByLabelText(/Thêm CSV hoặc XLSX/), file);

    const dialog = screen.getByRole("dialog", { name: "Quản lý bộ dữ liệu" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("File vượt quá giới hạn 10 MB.");
    expect(screen.queryByRole("button", { name: "Thêm bảng" })).not.toBeInTheDocument();
  });

  it("giữ hộp thoại và báo lỗi 409 khi tên bộ dữ liệu bị trùng", async () => {
    installApi({ importError: "Tên bộ dữ liệu đã tồn tại." });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Quản lý dữ liệu" }));

    await user.type(screen.getByLabelText("Tên bộ dữ liệu"), "Doanh số 2026");
    await user.click(screen.getByRole("button", { name: "Tạo workspace rỗng" }));

    const dialog = screen.getByRole("dialog", { name: "Quản lý bộ dữ liệu" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Tên bộ dữ liệu đã tồn tại.");
    expect(dialog).toBeInTheDocument();
    expect(screen.queryByText(/Đã cập nhật .* thành công/)).not.toBeInTheDocument();
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
    expect(screen.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();
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
    expect(await screen.findByText("Chưa thể trả lời")).toBeInTheDocument();
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
