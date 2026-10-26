import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";
import type { ChatResponse } from "../src/types";

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
  table_count: 1,
  document_count: 0,
  tables: [{
    dataset_table_id: 12, display_name: "sales", original_filename: "sales.csv",
    file_type: "csv", sheet_name: null, row_count: 2, column_count: 2,
    columns: [
      { source_name: "Sản phẩm", name: "san_pham", data_type: "TEXT" },
      { source_name: "Doanh thu", name: "doanh_thu", data_type: "BIGINT" },
    ],
  }],
  created_at: "2026-10-14T00:00:00Z",
};
const emptyWorkspace = {
  ...uploadedDataset,
  original_filename: null,
  file_type: null,
  row_count: null,
  column_count: null,
  columns: [],
  table_count: 0,
  tables: [],
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
  datasets: Array<typeof defaultDataset | typeof uploadedDataset | typeof emptyWorkspace>;
  messages: Array<Record<string, unknown>>;
  documents: Array<Record<string, unknown>>;
  messageRequests: number;
  previewPaths: string[];
  deletionPaths: string[];
  modelId: string;
  messageModels: string[];
  fallbackNext: boolean;
}

const runtimeErrors = new WeakMap<Page, { console: string[]; page: string[]; requests: string[]; responses: string[] }>();
const expectedDocumentDenials = new WeakMap<Page, number>();

test.beforeEach(async ({ page }, testInfo) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(testInfo.project.use.baseURL ?? "http://127.0.0.1:8080").origin,
  });
  const errors = { console: [] as string[], page: [] as string[], requests: [] as string[], responses: [] as string[] };
  runtimeErrors.set(page, errors);
  page.on("console", (message) => { if (message.type() === "error") errors.console.push(message.text()); });
  page.on("pageerror", (error) => errors.page.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") {
      errors.requests.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on("response", (response) => { if (response.status() >= 400) errors.responses.push(`${response.status()} ${response.url()}`); });
});

test.afterEach(async ({ page }) => {
  const errors = runtimeErrors.get(page);
  const denied = expectedDocumentDenials.get(page) ?? 0;
  expect(errors?.console ?? []).toEqual(Array.from({ length: denied }, () => "Failed to load resource: the server responded with a status of 403 (Forbidden)"));
  expect(errors?.page ?? []).toEqual([]);
  expect(errors?.requests ?? []).toEqual([]);
  expect(errors?.responses ?? []).toEqual(Array.from({ length: denied }, () => expect.stringMatching(/^403 http:\/\/127\.0\.0\.1:\d+\/api\/datasets\/7\/documents$/)));
});

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: status === 204 ? "" : JSON.stringify(body) });
}

function responseFor(question: string) {
  const normalized = question.toLocaleLowerCase("vi-VN");
  if (normalized.includes("đổi trả")) return ragResponse;
  if (normalized.includes("miễn phí vận chuyển")) return hybridResponse;
  if (normalized.includes("thời tiết")) {
    return { answer: "Mình chưa đủ thông tin để trả lời chính xác câu hỏi này. Bạn hãy kiểm tra dữ liệu hoặc liên kết bảng trong Quản lý dữ liệu nhé.", route: "UNSUPPORTED", sql: null, rows: [], sources: [], error: null };
  }
  return sqlResponse;
}

async function installApi(page: Page, options: { seed?: boolean; delayMs?: number; response?: Partial<ChatResponse> } = {}) {
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
    documents: [],
    messageRequests: 0,
    previewPaths: [],
    deletionPaths: [],
    modelId: "inetcloud-knowledge",
    messageModels: [],
    fallbackNext: false,
  };
  const summary = () => ({
    conversation_id: conversationId,
    title: state.title,
    dataset_id: null,
    dataset_name: "Dữ liệu cửa hàng mẫu",
    model_id: state.modelId,
    created_at: "2026-10-14T00:00:00Z",
    updated_at: "2026-10-14T00:00:02Z",
  });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/auth/me") return json(route, {
      user: { user_id: "mock-account-a", email: "a@example.invalid", display_name: "Mock account A" },
      csrf_token: "mock-csrf-token",
    });
    if (url.pathname === "/api/models") return json(route, {
      default_model: "inetcloud-knowledge", gemini_fallback_enabled: true,
      models: [
        { id: "inetcloud-knowledge", label: "iNetCloud Knowledge", provider: "inetcloud", configured: true },
        { id: "gemini", label: "Gemini", provider: "gemini", configured: true },
      ],
    });
    if (url.pathname === "/api/uploads/limits") return json(route, { max_file_bytes: 10485760, max_rows: 5000, max_columns: 30, max_pdf_pages: 100, provider_data_enabled: false, preview_per_hour: 180, upload_per_hour: 60 });
    if (url.pathname === "/api/health") return json(route, health);
    if (url.pathname === "/api/datasets" && method === "GET") return json(route, state.datasets);
    if (url.pathname === "/api/datasets" && method === "POST") {
      state.datasets = [defaultDataset, emptyWorkspace];
      return json(route, emptyWorkspace, 201);
    }
    if (
      (url.pathname === "/api/datasets/preview" ||
        url.pathname === "/api/datasets/7/tables/preview") &&
      method === "POST"
    ) {
      state.previewPaths.push(url.pathname);
      return json(route, {
        filename: "sales.csv", file_type: "csv", sheet_name: null, sheet_names: [],
        row_count: 2, column_count: 2, columns: uploadedDataset.columns,
        rows: [{ "Sản phẩm": "Áo linen", "Doanh thu": "120000" }], warnings: [],
      });
    }
    if (url.pathname === "/api/datasets/7/documents" && method === "GET") {
      return json(route, state.documents);
    }
    if (url.pathname === "/api/datasets/7" && method === "GET") {
      return json(route, state.datasets.find((item) => item.dataset_id === 7));
    }
    if (url.pathname === "/api/datasets/7/tables/12" && method === "DELETE") {
      state.deletionPaths.push(url.pathname);
      state.datasets = [defaultDataset, { ...emptyWorkspace, document_count: state.documents.length }];
      return json(route, null, 204);
    }
    if (url.pathname === "/api/datasets/7" && method === "DELETE") {
      state.deletionPaths.push(`${url.pathname}${url.search}`);
      state.datasets = [defaultDataset];
      state.documents = [];
      return json(route, null, 204);
    }
    if (url.pathname === "/api/datasets/7/documents" && method === "POST") {
      const filenames = ["policy.pdf", "policy.docx", "policy.txt", "policy.md"];
      const originalFilename = filenames[state.documents.length] ?? "policy.md";
      const document = {
        document_id: state.documents.length + 1,
        dataset_id: 7,
        original_filename: originalFilename,
        file_type: originalFilename.split(".").pop(),
        title: "Chính sách",
        chunk_count: 1,
        created_at: "2026-10-16T00:00:00Z",
      };
      state.documents = [document, ...state.documents];
      return json(route, document, 201);
    }
    if (/^\/api\/datasets\/7\/documents\/\d+$/.test(url.pathname) && method === "DELETE") {
      state.deletionPaths.push(url.pathname);
      const documentId = Number(url.pathname.split("/").pop());
      state.documents = state.documents.filter((item) => item.document_id !== documentId);
      return json(route, null, 204);
    }
    if (url.pathname === "/api/datasets/7/tables/import" && method === "POST") {
      state.datasets = [defaultDataset, uploadedDataset];
      return json(route, uploadedDataset, 201);
    }
    if (url.pathname === "/api/conversations" && method === "GET") return json(route, state.exists ? [summary()] : []);
    if (url.pathname === "/api/conversations" && method === "POST") {
      state.modelId = request.postDataJSON().model_id ?? "inetcloud-knowledge";
      state.exists = true;
      state.messages = [];
      return json(route, summary(), 201);
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "GET") {
      return state.exists ? json(route, { ...summary(), messages: state.messages }) : json(route, { detail: "Không tìm thấy." }, 404);
    }
    if (url.pathname === `/api/conversations/${conversationId}` && method === "PATCH") {
      if (request.postDataJSON().model_id) {
        state.modelId = request.postDataJSON().model_id;
        return json(route, summary());
      }
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
      expect(request.postDataJSON()).not.toHaveProperty("route_hint");
      const question = String(request.postDataJSON().message);
      const requestedModel = request.postDataJSON().model_id ?? state.modelId;
      state.messageModels.push(requestedModel);
      state.modelId = requestedModel;
      const response = {
        ...responseFor(question), ...options.response, requested_model: requestedModel,
        used_model: options.response?.error ? null : state.fallbackNext ? "gemini" : requestedModel,
        fallback_used: state.fallbackNext,
        fallback_reason: state.fallbackNext ? "primary_provider_unavailable" : null,
      };
      state.fallbackNext = false;
      if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs));
      state.title = question.slice(0, 56);
      const userMessage = { message_id: state.messages.length + 1, role: "user", content: question, response: null, created_at: "2026-10-14T00:00:03Z" };
      const assistantMessage = { message_id: state.messages.length + 2, role: response.error ? "error" : "assistant", content: response.answer, response, created_at: "2026-10-14T00:00:04Z" };
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

async function waitForDrawerClosed(page: Page) {
  if ((page.viewportSize()?.width ?? 0) <= 800) {
    await expect.poll(async () => {
      const box = await page.locator(".sidebar").boundingBox();
      return box ? box.x + box.width : 0;
    }).toBeLessThanOrEqual(0);
  }
}

async function closeSidebar(page: Page) {
  const close = page.getByRole("button", { name: "Đóng thanh điều hướng" });
  if (await close.isVisible()) {
    await close.click();
    await waitForDrawerClosed(page);
  }
}

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
  const viewport = page.viewportSize()?.width ?? dimensions.viewport;
  expect(dimensions.document).toBeLessThanOrEqual(viewport);
  const main = await page.locator(".chat-main").evaluate((element) => ({ scroll: element.scrollWidth, visible: element.clientWidth }));
  expect(main.visible).toBeLessThanOrEqual(viewport);
  expect(main.scroll).toBeLessThanOrEqual(main.visible);
}

async function expectComposerLayout(page: Page, singleLine = true) {
  const box = await page.locator(".composer-box").boundingBox();
  const input = await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").boundingBox();
  const selector = await page.getByLabel("Chọn mô hình AI").boundingBox();
  const send = await page.getByRole("button", { name: "Gửi câu hỏi" }).boundingBox();
  expect(box).not.toBeNull();
  expect(input).not.toBeNull();
  expect(selector).not.toBeNull();
  expect(send).not.toBeNull();
  if (!box || !input || !selector || !send) throw new Error("Composer controls must be measurable.");
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  expect(input.width).toBeGreaterThanOrEqual(100);
  expect(input.x + input.width).toBeLessThanOrEqual(selector.x);
  expect(selector.x + selector.width).toBeLessThanOrEqual(send.x);
  for (const control of [input, selector, send]) {
    expect(control.x).toBeGreaterThanOrEqual(box.x);
    expect(control.y).toBeGreaterThanOrEqual(box.y);
    expect(control.x + control.width).toBeLessThanOrEqual(box.x + box.width);
    expect(control.y + control.height).toBeLessThanOrEqual(box.y + box.height);
    expect(Math.abs(control.y + control.height / 2 - box.y - box.height / 2)).toBeLessThanOrEqual(2);
  }
  if (singleLine) {
    expect(box.height).toBeGreaterThanOrEqual(58);
    expect(box.height).toBeLessThanOrEqual(68);
  } else {
    expect(box.height).toBeGreaterThan(68);
    expect(input.height).toBeLessThanOrEqual(160);
  }
  await expectNoPageOverflow(page);
}

test("responsive shell, drawer and composer keyboard behavior", async ({ page }, testInfo: TestInfo) => {
  await installApi(page);
  await openApp(page);
  await expect(page.getByText("Khám phá dữ liệu, phân tích kinh doanh và tra cứu thông tin bằng AI.")).toBeVisible();
  await expectComposerLayout(page);
  await page.screenshot({ path: testInfo.outputPath("empty-chat.png"), fullPage: true });
  await openSidebar(page);
  await expect(page.getByText("ShopQuery AI", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Đoạn chat mới" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Dữ liệu" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("empty-sidebar-open.png"), fullPage: true });

  const mobileClose = page.getByRole("button", { name: "Đóng thanh điều hướng" });
  if (await mobileClose.isVisible()) {
    await expect(page.locator(".sidebar")).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
    await page.screenshot({ path: testInfo.outputPath("mobile-drawer.png"), fullPage: true });
    await mobileClose.click();
  } else {
    await page.getByRole("button", { name: "Thu gọn sidebar" }).click();
    await expect(page.getByRole("button", { name: "Mở rộng sidebar" })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("empty-sidebar-collapsed.png"), fullPage: true });
    await page.getByRole("button", { name: "Mở rộng sidebar" }).click();
  }

  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await page.screenshot({ path: testInfo.outputPath("input-unfocused.png"), fullPage: true });
  await input.focus();
  await expect(input).toBeFocused();
  const inputFocus = await input.evaluate((element) => getComputedStyle(element).outlineStyle);
  const composerFocus = await page.locator(".composer-box").evaluate((element) => getComputedStyle(element).boxShadow);
  expect(inputFocus).toBe("none");
  expect(composerFocus).not.toBe("none");
  await page.screenshot({ path: testInfo.outputPath("input-focused.png"), fullPage: true });
  await input.fill("Dòng một");
  await expectComposerLayout(page);
  await page.screenshot({ path: testInfo.outputPath("input-single-line.png"), fullPage: true });
  await input.press("Shift+Enter");
  await input.type("Dòng hai");
  await expect(input).toHaveValue("Dòng một\nDòng hai");
  await expectComposerLayout(page, false);
  await page.screenshot({ path: testInfo.outputPath("input-multiline.png"), fullPage: true });
  await input.fill(Array.from({ length: 20 }, (_, index) => `Dòng ${index + 1}`).join("\n"));
  await expectComposerLayout(page, false);
  expect(await input.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await input.fill("");
  await expectComposerLayout(page);

  await page.getByRole("button", { name: /Chọn bộ dữ liệu/ }).click();
  await expect(page.getByRole("menu", { name: "Chọn bộ dữ liệu" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("dataset-dropdown.png"), fullPage: true });
  await page.keyboard.press("Escape");
  await expectNoPageOverflow(page);
});

test("creates chat once and renders SQL evidence with history controls", async ({ page }, testInfo) => {
  const state = await installApi(page, { delayMs: 150 });
  await openApp(page);
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Top sản phẩm");
  await input.press("Enter");
  await expect(page.getByLabel("ShopQuery AI đang xử lý")).toBeVisible();
  await expect(page.getByText(sqlResponse.answer)).toBeVisible();
  expect(state.messageRequests).toBe(1);
  const firstResponse = page.locator(".message--assistant").nth(0);
  const sqlCode = firstResponse.getByText(/SELECT product_name/);
  const table = firstResponse.getByRole("region", { name: "Kết quả truy vấn" });
  const tableControl = firstResponse.getByRole("button", { name: "Bảng dữ liệu · 2" });
  const sqlControl = firstResponse.getByRole("button", { name: "Xem SQL" });
  await expect(tableControl).toHaveAttribute("aria-expanded", "false");
  await expect(sqlControl).toHaveAttribute("aria-expanded", "false");
  await expect(sqlCode).toHaveCount(0);
  await expect(table).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("user-message-short.png"), fullPage: true });
  await page.screenshot({ path: testInfo.outputPath("sql-result-collapsed.png"), fullPage: true });

  await tableControl.click();
  await expect(tableControl).toHaveAttribute("aria-expanded", "true");
  await expect(table).toBeVisible();
  await expect(table).toContainText("Điện thoại SQ 010");
  await expect(sqlCode).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("sql-result-expanded.png"), fullPage: true });
  if ((page.viewportSize()?.width ?? 1_000) <= 390) {
    await page.screenshot({ path: testInfo.outputPath("mobile-sql-table-expanded.png"), fullPage: true });
  }
  await sqlControl.click();
  await expect(tableControl).toHaveAttribute("aria-expanded", "false");
  await expect(sqlControl).toHaveAttribute("aria-expanded", "true");
  await expect(sqlCode).toBeVisible();
  await expect(table).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("sql-code-expanded.png"), fullPage: true });
  await firstResponse.getByRole("button", { name: "Sao chép SQL" }).click();
  await expect(firstResponse.getByRole("button", { name: "Sao chép SQL" })).toContainText("Đã sao chép");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(sqlResponse.sql);
  await sqlControl.click();
  await expect(sqlControl).toHaveAttribute("aria-expanded", "false");
  await expect(sqlCode).toHaveCount(0);

  await openSidebar(page);
  const menu = page.getByRole("button", { name: /Tùy chọn cho Top sản phẩm/ });
  await menu.click();
  await page.getByRole("menuitem", { name: /Đổi tên/ }).click();
  await page.getByRole("textbox", { name: "Tên cuộc trò chuyện" }).fill("Báo cáo bán hàng");
  await page.getByRole("button", { name: "Lưu tên" }).click();
  await expect(page.getByText("Báo cáo bán hàng").first()).toBeVisible();
  await closeSidebar(page);

  const longQuestion = "Hãy phân tích chi tiết các sản phẩm bán chạy nhất, so sánh số lượng và giải thích những điểm nổi bật trong dữ liệu tháng này.";
  await input.fill(longQuestion);
  await input.press("Enter");
  await expect(page.getByText(longQuestion)).toBeVisible();
  await expect(page.getByText(sqlResponse.answer)).toHaveCount(2);
  await expect(page.locator(".message--assistant")).toHaveCount(2);
  const secondResponse = page.locator(".message--assistant").nth(1);
  await expect(secondResponse.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
  await firstResponse.getByRole("button", { name: "Bảng dữ liệu · 2" }).click();
  await expect(firstResponse.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();
  await expect(secondResponse.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("user-message-long.png"), fullPage: true });
  if ((page.viewportSize()?.width ?? 1_000) <= 390) {
    await page.screenshot({ path: testInfo.outputPath("mobile-conversation.png"), fullPage: true });
  }
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("conversation-sql.png"), fullPage: true });
});

test("restores history and keeps RAG, Hybrid, Unsupported evidence truthful", async ({ page }, testInfo) => {
  await installApi(page, { seed: true });
  await openApp(page);
  await expect(page.getByText(sqlResponse.answer)).toBeVisible();

  await openSidebar(page);
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await waitForDrawerClosed(page);
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Chính sách đổi trả như thế nào?");
  await input.press("Enter");
  const ragMessage = page.locator(".message--assistant").last();
  const ragSources = ragMessage.getByRole("button", { name: "Nguồn · 1" });
  await expect(ragSources).toHaveAttribute("aria-expanded", "false");
  await expect(ragMessage.getByText("return_policy.md")).toHaveCount(0);
  await ragSources.focus();
  await ragSources.press("Enter");
  await expect(ragSources).toHaveAttribute("aria-expanded", "true");
  await expect(ragMessage.getByLabel("Nguồn tham khảo")).toContainText("return_policy.md");
  await page.screenshot({ path: testInfo.outputPath("rag-sources-expanded.png"), fullPage: true });

  await openSidebar(page);
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await waitForDrawerClosed(page);
  await input.fill("Sản phẩm bán chạy có được miễn phí vận chuyển không?");
  await input.press("Enter");
  await expect(page.getByText("SQL + Tài liệu")).toBeVisible();
  const hybridMessage = page.locator(".message--assistant").last();
  const hybridRows = hybridMessage.getByRole("button", { name: "Bảng dữ liệu · 1" });
  const hybridSql = hybridMessage.getByRole("button", { name: "Xem SQL" });
  const hybridSources = hybridMessage.getByRole("button", { name: "Nguồn · 1" });
  await expect(hybridRows).toHaveAttribute("aria-expanded", "false");
  await expect(hybridSql).toHaveAttribute("aria-expanded", "false");
  await expect(hybridSources).toHaveAttribute("aria-expanded", "false");
  await expect(hybridMessage.getByText(/SELECT product_name/)).toHaveCount(0);
  await expect(hybridMessage.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
  await expect(hybridMessage.getByLabel("Nguồn tham khảo")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("hybrid-collapsed.png"), fullPage: true });
  if ((page.viewportSize()?.width ?? 1_000) <= 390) {
    await page.screenshot({ path: testInfo.outputPath("mobile-evidence-toolbar.png"), fullPage: true });
  }

  await hybridRows.click();
  await expect(hybridMessage.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("hybrid-table-expanded.png"), fullPage: true });
  await hybridSql.click();
  await expect(hybridMessage.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
  await expect(hybridMessage.getByText(/SELECT product_name/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("hybrid-sql-expanded.png"), fullPage: true });
  await hybridSources.click();
  await expect(hybridMessage.getByText(/SELECT product_name/)).toHaveCount(0);
  await expect(hybridMessage.getByLabel("Nguồn tham khảo")).toContainText("shipping_policy.md");
  await page.screenshot({ path: testInfo.outputPath("hybrid-sources-expanded.png"), fullPage: true });
  await hybridSources.click();
  await expect(hybridMessage.getByLabel("Nguồn tham khảo")).toHaveCount(0);

  await openSidebar(page);
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await waitForDrawerClosed(page);
  await input.fill("Thời tiết ngày mai?");
  await input.press("Enter");
  await expect(page.getByText("Chưa thể trả lời", { exact: true })).toBeVisible();
  await expect(page.getByText("Mình chưa đủ thông tin để trả lời chính xác câu hỏi này.", { exact: false })).toBeVisible();
  await openApp(page);
  await expect(page.getByText("Chưa thể trả lời", { exact: true })).toBeVisible();
  await expect(page.getByRole("group", { name: "Bằng chứng hỗ trợ" })).toHaveCount(0);
  await expectNoPageOverflow(page);
});

test("selects models, preserves attribution and restores a fallback conversation", async ({ page }, testInfo) => {
  const state = await installApi(page);
  await openApp(page);
  const selector = page.getByLabel("Chọn mô hình AI");
  await expect(selector).toHaveValue("inetcloud-knowledge");
  await expect(selector).toHaveAttribute("title", "iNetCloud Knowledge");
  await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").focus();
  await page.keyboard.press("Tab");
  await expect(selector).toBeFocused();
  await selector.press("Alt+ArrowDown");
  await page.screenshot({ path: testInfo.outputPath("model-selector-open.png"), fullPage: true });
  await page.keyboard.press("Escape");
  await selector.focus();
  await expect(selector).toBeFocused();
  await page.keyboard.press("Escape");
  await selector.selectOption("gemini");
  await expect(selector).toHaveAttribute("title", "Gemini");
  await page.screenshot({ path: testInfo.outputPath("model-gemini-selected.png"), fullPage: true });
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Top sản phẩm");
  await selector.focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Gửi câu hỏi" })).toBeFocused();
  await input.press("Enter");
  await expect(page.locator(".model-attribution").last()).toHaveText("Gemini");
  expect(state.messageModels).toEqual(["gemini"]);
  await selector.selectOption("inetcloud-knowledge");
  await expect.poll(() => state.modelId).toBe("inetcloud-knowledge");
  await page.screenshot({ path: testInfo.outputPath("model-knowledge-selected.png"), fullPage: true });
  state.fallbackNext = true;
  await input.fill("Chính sách đổi trả như thế nào?");
  await input.press("Enter");
  await expect(page.getByText(/Đã chuyển từ Knowledge sang Gemini/)).toBeVisible();
  expect(state.messageModels).toEqual(["gemini", "inetcloud-knowledge"]);
  await page.reload();
  await expect(page.getByText(/Đã chuyển từ Knowledge sang Gemini/)).toBeVisible();
  await expect(selector).toHaveValue("inetcloud-knowledge");
  await expect(page.locator(".model-attribution")).toHaveText(["Gemini", "Gemini"]);
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("model-selector-fallback.png"), fullPage: true });
});

test("renders long Markdown answers without unsafe markup or horizontal page overflow", async ({ page }, testInfo) => {
  const url = `https://example.com/policy/${"chi-tiet-".repeat(24)}`;
  const answer = [
    "Báo cáo minh họa với **dữ liệu kiểm thử**, không phải dữ liệu bán hàng thực.",
    Array.from({ length: 20 }, (_, index) => `${index + 1}. **Sản phẩm mẫu ${index + 1}** — ${20 - index} đơn vị. Mô tả tiếng Việt để kiểm tra khả năng đọc danh sách dài.`).join("\n"),
    "Các điều kiện tham khảo:\n\n- Giữ hóa đơn mua hàng.\n- Kiểm tra chính sách áp dụng.",
    `Chuỗi dài: ${"sanpham".repeat(40)}`,
    `Tài liệu: ${url}`,
    `Ví dụ mã \`quantity\`:\n\n\`\`\`sql\nSELECT '${"x".repeat(240)}' AS example;\n\`\`\``,
    "| Sản phẩm | Số lượng | Danh mục | Chính sách |\n| --- | --- | --- | --- |\n| Áo linen mẫu | 42 | Thời trang | Đối chiếu điều kiện đổi trả |",
    '[Liên kết bị chặn](javascript:alert%281%29)\n\n<script>window.markdownExecuted = true</script>\n\n![Mô tả ảnh](https://example.com/tracker.png)',
  ].join("\n\n");
  await installApi(page, { response: { answer } });
  await openApp(page);
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("**Câu hỏi nguyên văn** <script>không thực thi</script>");
  await input.press("Enter");
  const content = page.locator(".assistant-content");
  await expect(content.locator("ol > li")).toHaveCount(20);
  await expect(content.locator("ul > li")).toHaveCount(2);
  await expect(content.locator("strong").first()).toHaveText("dữ liệu kiểm thử");
  await expect(page.locator(".message--user .message-text")).toHaveText("**Câu hỏi nguyên văn** <script>không thực thi</script>");
  await expect(content.locator("img, script, iframe")).toHaveCount(0);
  await expect(content.getByRole("link", { name: "Liên kết bị chặn" })).toHaveCount(0);
  const link = content.getByRole("link", { name: url });
  await expect(link).toHaveAttribute("href", url);
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  const code = content.locator("pre");
  expect(await code.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  await code.focus();
  await expect(code).toBeFocused();
  await code.press("End");
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("markdown-code.png"), fullPage: true });
  const table = content.getByRole("region", { name: "Bảng trong câu trả lời" });
  await table.focus();
  await expect(table).toBeFocused();
  if ((page.viewportSize()?.width ?? 1440) <= 390) {
    expect(await table.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
    await table.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
    expect(await table.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  }
  await expectComposerLayout(page);
  await page.screenshot({ path: testInfo.outputPath("markdown-table.png"), fullPage: true });
  await page.locator(".chat-main").evaluate((element) => { element.scrollTop = 0; });
  await expect(content.locator("ol li").first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("long-answer-list.png"), fullPage: true });
});

test("keeps composer usable at zoom-equivalent viewports and on short mobile screens", async ({ page }, testInfo) => {
  await installApi(page);
  await openApp(page);
  if ((page.viewportSize()?.width ?? 0) >= 1280) {
    const original = page.viewportSize()!;
    for (const zoom of [1.25, 1.5]) {
      await page.setViewportSize({ width: Math.floor(original.width / zoom), height: Math.floor(original.height / zoom) });
      await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").fill("Câu hỏi");
      const metrics = await page.locator(".composer-box").evaluate((box) => {
        const controls = [box.querySelector("textarea"), box.querySelector("select"), box.querySelector("button")];
        const bounds = box.getBoundingClientRect();
        return {
          right: bounds.right,
          bottom: bounds.bottom,
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
          contained: controls.every((element) => {
            if (!element) return false;
            const rect = element.getBoundingClientRect();
            return rect.left >= bounds.left && rect.right <= bounds.right && rect.top >= bounds.top && rect.bottom <= bounds.bottom;
          }),
        };
      });
      expect(metrics.contained).toBe(true);
      expect(metrics.right).toBeLessThanOrEqual(metrics.viewportWidth);
      expect(metrics.bottom).toBeLessThanOrEqual(metrics.viewportHeight);
      await page.screenshot({ path: testInfo.outputPath(`zoom-equivalent-${zoom * 100}.png`), fullPage: true });
    }
  } else {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 420 });
    const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
    await input.fill("Câu hỏi");
    await expectComposerLayout(page);
    await expect(page.getByRole("button", { name: "Gửi câu hỏi" })).toBeInViewport();
    await page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" }).scrollIntoViewIfNeeded();
    await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeInViewport();
    await page.getByRole("button", { name: /Kết hợp dữ liệu:/ }).scrollIntoViewIfNeeded();
    await expect(page.getByRole("button", { name: /Kết hợp dữ liệu:/ })).toBeInViewport();
    await page.screenshot({ path: testInfo.outputPath("short-screen.png"), fullPage: true });
  }
});

test("shows provider failures without invented answers or evidence", async ({ page }, testInfo) => {
  await installApi(page, { response: {
    answer: "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.", route: null, sql: null, rows: [], sources: [],
    error: "Knowledge tạm thời không khả dụng.",
  } });
  await openApp(page);
  await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").fill("Top sản phẩm");
  await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
  await expect(page.getByRole("alert")).toHaveText("Knowledge tạm thời không khả dụng.");
  await expect(page.locator(".assistant-content")).toHaveCount(0);
  await expect(page.locator(".model-attribution, .route-badge")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Bằng chứng hỗ trợ" })).toHaveCount(0);
  await expectComposerLayout(page);
  await page.screenshot({ path: testInfo.outputPath("provider-error.png"), fullPage: true });
});

test("previews and imports a CSV before selecting the uploaded dataset", async ({ page }) => {
  const state = await installApi(page);
  await openApp(page);
  await openSidebar(page);
  await page.getByRole("button", { name: "Quản lý dữ liệu" }).click();
  await page.getByLabel("Tên bộ dữ liệu").fill("Doanh số 2026");
  await page.getByRole("button", { name: "Tạo workspace rỗng" }).click();
  await page.getByLabel(/Thêm CSV hoặc XLSX/).setInputFiles("e2e/fixtures/sales.csv");
  await expect(page.getByText("120000")).toBeVisible();
  expect(state.previewPaths).toEqual(["/api/datasets/7/tables/preview"]);
  await expect(page.locator(".preview-stats span").filter({ hasText: "2 dòng" })).toBeVisible();
  await page.getByRole("button", { name: "Thêm bảng" }).click();
  await expect(page.getByText("Đã cập nhật Doanh số 2026 thành công.")).toBeVisible();
  const documentInput = page.getByLabel(/Thêm PDF, DOCX, TXT hoặc MD/);
  for (const filename of ["policy.pdf", "policy.docx", "policy.txt", "policy.md"]) {
    await documentInput.setInputFiles(`e2e/fixtures/${filename}`);
    await expect(page.getByText(filename)).toBeVisible();
  }
  await expect(page.getByText("4 tài liệu")).toBeVisible();
  await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
  await expect(page.getByRole("button", { name: /Chọn bộ dữ liệu.*Doanh số 2026/ })).toBeVisible();
  await expectNoPageOverflow(page);
});

test("authenticated file selection survives same-session focus and provider gate explains document refusal", async ({ page }, info) => {
  expectedDocumentDenials.set(page, 2);
  const state = await installApi(page);
  let documentCalls = 0;
  await page.route("**/api/datasets/7/documents", async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    documentCalls++;
    return route.fulfill({ status: 403, json: { detail: "Quản trị viên chưa cho phép gửi dữ liệu tới AI providers." } });
  });
  await openApp(page);
  await openSidebar(page);
  await page.getByRole("button", { name: "Quản lý dữ liệu" }).click();
  await page.getByLabel("Tên bộ dữ liệu").fill("Giả lập kiểm tra focus");
  await page.getByRole("button", { name: "Tạo workspace rỗng" }).click();
  await page.getByLabel(/Thêm CSV hoặc XLSX/).setInputFiles("e2e/fixtures/sales.csv");
  await expect(page.getByText("120000")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("120000")).toBeVisible();
  await page.getByRole("button", { name: "Thêm bảng", exact: true }).click();
  await expect(page.getByText("Đã cập nhật Doanh số 2026 thành công.")).toBeVisible();
  expect(state.previewPaths).toHaveLength(1);
  await expect(page.getByText(/Lưu tài liệu cần Gemini Embedding/)).toBeVisible();
  for (const filename of ["policy.pdf", "policy.docx"]) {
    await page.getByLabel(/Thêm PDF, DOCX, TXT hoặc MD/).setInputFiles(`e2e/fixtures/${filename}`);
    await expect(page.getByRole("alert")).toContainText("chưa cho phép");
  }
  expect(documentCalls).toBe(2);
  expect(state.documents).toHaveLength(0);
  await page.screenshot({ path: info.outputPath("authenticated-upload-gate.png") });
  await expectNoPageOverflow(page);
});

test("confirms deletion of individual sources and the selected workspace", async ({ page }, testInfo) => {
  const state = await installApi(page);
  state.datasets = [defaultDataset, { ...uploadedDataset, document_count: 1 }];
  state.documents = [{ document_id: 4, dataset_id: 7, original_filename: "policy.md",
    file_type: "md", title: "Policy", chunk_count: 1, created_at: "2026-10-19T00:00:00Z" }];
  await openApp(page);
  await openSidebar(page);
  await page.getByRole("button", { name: "Quản lý dữ liệu", exact: true }).click();
  await page.getByRole("tab", { name: "Quản lý bộ hiện có", exact: true }).click();
  await page.getByRole("button", { name: "Xóa bảng sales", exact: true }).click();
  await expect(page.getByRole("region", { name: "Xác nhận xóa dữ liệu" })).toBeInViewport();
  await expectNoPageOverflow(page);
  await page.getByRole("button", { name: "Hủy xóa", exact: true }).click();
  expect(state.deletionPaths).toEqual([]);
  await page.getByRole("button", { name: "Xóa bảng sales", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận xóa vĩnh viễn", exact: true }).click();
  await expect(page.getByText("Chưa có bảng dữ liệu.")).toBeVisible();
  await expect(page.getByText("policy.md", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Xóa tài liệu policy.md", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận xóa vĩnh viễn", exact: true }).click();
  await expect(page.getByText("Chưa có tài liệu.")).toBeVisible();
  await page.getByRole("button", { name: "Xóa bộ dữ liệu", exact: true }).click();
  await page.getByRole("checkbox", { name: /Xóa cả lịch sử chat/ }).check();
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("workspace-delete-confirm.png"), fullPage: true });
  await page.getByRole("button", { name: "Xác nhận xóa vĩnh viễn", exact: true }).click();
  await expect(page.getByText(/Đã xóa Doanh số 2026/)).toBeVisible();
  expect(state.deletionPaths).toEqual([
    "/api/datasets/7/tables/12", "/api/datasets/7/documents/4",
    "/api/datasets/7?delete_conversations=true",
  ]);
  await expect(page.getByRole("combobox", { name: "Bộ dữ liệu", exact: true })).toHaveValue("");
  await expectNoPageOverflow(page);
});
