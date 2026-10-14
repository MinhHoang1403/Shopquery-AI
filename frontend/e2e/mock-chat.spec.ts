import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";

const conversationId = "11111111-1111-4111-8111-111111111111";
const health = { status: "ok", service: "ShopQuery AI" };
const defaultDataset = {
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
const uploadedDataset = {
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

const sqlResponse = {
  answer: "Top sản phẩm đã được tổng hợp từ dữ liệu bán hàng.",
  route: "SQL",
  sql: "SELECT product_name, total_quantity FROM sales ORDER BY total_quantity DESC LIMIT 5",
  rows: [
    { product_name: "Điện thoại SQ 010", total_quantity: 15 },
    { product_name: "Thiết bị âm thanh SQ 009", total_quantity: 14 },
  ],
  sources: [],
  error: null,
};
const ragResponse = {
  answer: "Cửa hàng tiếp nhận yêu cầu đổi trả trong vòng 14 ngày.",
  route: "RAG",
  sql: null,
  rows: [],
  sources: [{ chunk_id: 310, source_file: "return_policy.md", section_title: "Thời hạn đổi trả", content: "Yêu cầu đổi trả phải được gửi trong vòng 14 ngày." }],
  error: null,
};
const hybridResponse = {
  answer: "Laptop SQ 018 thuộc danh mục được miễn phí vận chuyển.",
  route: "HYBRID",
  sql: "SELECT product_name, category_code FROM sales ORDER BY total_quantity DESC LIMIT 5",
  rows: [{ product_name: "Laptop SQ 018 phiên bản cấu hình cao", category_code: "LAPTOP", comparison_status: "Được miễn phí vận chuyển tiêu chuẩn" }],
  sources: [{ chunk_id: 315, source_file: "shipping_policy.md", section_title: "Miễn phí vận chuyển", content: "Danh mục laptop được miễn phí vận chuyển tiêu chuẩn." }],
  error: null,
};

interface ApiState {
  title: string;
  exists: boolean;
  datasets: typeof defaultDataset[] | (typeof defaultDataset | typeof uploadedDataset)[];
  messages: Array<Record<string, unknown>>;
  messageRequests: number;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: status === 204 ? "" : JSON.stringify(body) });
}

function responseFor(question: string) {
  const normalized = question.toLocaleLowerCase("vi-VN");
  if (normalized.includes("đổi trả")) return ragResponse;
  if (normalized.includes("miễn phí vận chuyển")) return hybridResponse;
  if (normalized.includes("thời tiết")) {
    return { answer: "Yêu cầu nằm ngoài phạm vi dữ liệu cửa hàng.", route: "UNSUPPORTED", sql: null, rows: [], sources: [], error: null };
  }
  return sqlResponse;
}

async function installApi(page: Page, options: { seed?: boolean; delayMs?: number } = {}) {
  const state: ApiState = {
    title: options.seed ? "Doanh thu tháng 9" : "Cuộc trò chuyện mới",
    exists: Boolean(options.seed),
    datasets: [defaultDataset],
    messages: options.seed
      ? [
          { message_id: 1, role: "user", content: "Doanh thu tháng 9?", response: null, created_at: "2026-10-14T00:00:01Z" },
          { message_id: 2, role: "assistant", content: sqlResponse.answer, response: sqlResponse, created_at: "2026-10-14T00:00:02Z" },
        ]
      : [],
    messageRequests: 0,
  };
  const summary = () => ({
    conversation_id: conversationId,
    title: state.title,
    dataset_id: null,
    dataset_name: "Dữ liệu cửa hàng mẫu",
    created_at: "2026-10-14T00:00:00Z",
    updated_at: "2026-10-14T00:00:02Z",
  });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/health") return json(route, health);
    if (url.pathname === "/api/datasets" && method === "GET") return json(route, state.datasets);
    if (url.pathname === "/api/datasets/preview" && method === "POST") {
      return json(route, {
        filename: "sales.csv", file_type: "csv", sheet_name: null, sheet_names: [],
        row_count: 2, column_count: 2, columns: uploadedDataset.columns,
        rows: [{ "Sản phẩm": "Áo linen", "Doanh thu": "120000" }], warnings: [],
      });
    }
    if (url.pathname === "/api/datasets/import" && method === "POST") {
      state.datasets = [defaultDataset, uploadedDataset];
      return json(route, uploadedDataset, 201);
    }
    if (url.pathname === "/api/conversations" && method === "GET") return json(route, state.exists ? [summary()] : []);
    if (url.pathname === "/api/conversations" && method === "POST") {
      state.exists = true;
      state.messages = [];
      return json(route, summary(), 201);
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "GET") {
      return state.exists ? json(route, { ...summary(), messages: state.messages }) : json(route, { detail: "Không tìm thấy." }, 404);
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "PATCH") {
      state.title = String(request.postDataJSON().title);
      return json(route, summary());
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "DELETE") {
      state.exists = false;
      state.messages = [];
      return json(route, null, 204);
    }
    if (url.pathname === `/api/conversations/${conversationId}/messages` && method === "POST") {
      state.messageRequests += 1;
      const question = String(request.postDataJSON().message);
      const response = responseFor(question);
      if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs));
      state.title = question.slice(0, 56);
      const userMessage = { message_id: state.messages.length + 1, role: "user", content: question, response: null, created_at: "2026-10-14T00:00:03Z" };
      const assistantMessage = { message_id: state.messages.length + 2, role: "assistant", content: response.answer, response, created_at: "2026-10-14T00:00:04Z" };
      state.messages.push(userMessage, assistantMessage);
      return json(route, { conversation: summary(), user_message: userMessage, assistant_message: assistantMessage });
    }
    return json(route, { detail: `Unmocked ${method} ${url.pathname}` }, 404);
  });
  return state;
}

async function openApp(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
}

async function openSidebar(page: Page) {
  if (await page.getByRole("button", { name: "Mở thanh điều hướng" }).isVisible()) {
    await page.getByRole("button", { name: "Mở thanh điều hướng" }).click();
  }
}

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
}

test("responsive shell, drawer and composer keyboard behavior", async ({ page }, testInfo: TestInfo) => {
  await installApi(page);
  await openApp(page);
  await openSidebar(page);
  await expect(page.getByText("ShopQuery AI", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Đoạn chat mới" })).toBeVisible();

  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Dòng một");
  await input.press("Shift+Enter");
  await input.type("Dòng hai");
  await expect(input).toHaveValue("Dòng một\nDòng hai");
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("shell.png"), fullPage: true });
});

test("creates chat once and renders SQL evidence with history controls", async ({ page }) => {
  const state = await installApi(page, { delayMs: 150 });
  await openApp(page);
  await page.getByRole("button", { name: /Phân tích bán hàng/ }).click();
  await expect(page.getByLabel("ShopQuery AI đang xử lý")).toBeVisible();
  await expect(page.getByText(sqlResponse.answer)).toBeVisible();
  expect(state.messageRequests).toBe(1);
  await page.locator("details.sql-card summary").click();
  await expect(page.getByText(/SELECT product_name/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Kết quả truy vấn" })).toContainText("Điện thoại SQ 010");

  await openSidebar(page);
  const menu = page.getByRole("button", { name: /Tùy chọn cho Top 5 sản phẩm/ });
  await menu.click();
  await page.getByRole("menuitem", { name: /Đổi tên/ }).click();
  await page.getByRole("textbox", { name: "Tên cuộc trò chuyện" }).fill("Báo cáo bán hàng");
  await page.getByRole("button", { name: "Lưu tên" }).click();
  await expect(page.getByText("Báo cáo bán hàng").first()).toBeVisible();
  await expectNoPageOverflow(page);
});

test("restores history and keeps RAG, Hybrid, Unsupported evidence truthful", async ({ page }) => {
  await installApi(page, { seed: true });
  await openApp(page);
  await expect(page.getByText(sqlResponse.answer)).toBeVisible();

  await openSidebar(page);
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Chính sách đổi trả như thế nào?");
  await input.press("Enter");
  await expect(page.getByLabel("Nguồn tham khảo")).toContainText("return_policy.md");

  await openSidebar(page);
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await input.fill("Sản phẩm bán chạy có được miễn phí vận chuyển không?");
  await input.press("Enter");
  await expect(page.getByText("SQL + Tài liệu")).toBeVisible();
  await expect(page.getByLabel("Nguồn tham khảo")).toContainText("shipping_policy.md");

  await openSidebar(page);
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await input.fill("Thời tiết ngày mai?");
  await input.press("Enter");
  await expect(page.getByText("Ngoài phạm vi", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Nguồn tham khảo")).toHaveCount(0);
  await expectNoPageOverflow(page);
});

test("previews and imports a CSV before selecting the uploaded dataset", async ({ page }) => {
  await installApi(page);
  await openApp(page);
  await openSidebar(page);
  await page.getByRole("button", { name: "Nạp dữ liệu mới" }).click();
  await page.getByLabel(/Chọn file CSV hoặc XLSX/).setInputFiles("e2e/fixtures/sales.csv");
  await expect(page.getByText("120000")).toBeVisible();
  await expect(page.locator(".preview-stats span").filter({ hasText: "2 dòng" })).toBeVisible();
  await page.getByRole("button", { name: "Xác nhận import" }).click();
  await expect(page.getByText("Đã import Doanh số 2026 thành công.")).toBeVisible();
  await expect(page.getByText(/Đang sử dụng/)).toContainText("Doanh số 2026");
  await expectNoPageOverflow(page);
});
