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
  modelId: string;
  messageModels: string[];
  fallbackNext: boolean;
}

const runtimeErrors = new WeakMap<Page, { console: string[]; page: string[]; requests: string[]; responses: string[] }>();

test.beforeEach(async ({ page }, testInfo) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(testInfo.project.use.baseURL ?? "http://127.0.0.1:8080").origin,
  });
  const errors = { console: [] as string[], page: [] as string[], requests: [] as string[], responses: [] as string[] };
  runtimeErrors.set(page, errors);
  page.on("console", (message) => { if (message.type() === "error") errors.console.push(message.text()); });
  page.on("pageerror", (error) => errors.page.push(error.message));
  page.on("requestfailed", (request) => errors.requests.push(`${request.method()} ${request.url()}`));
  page.on("response", (response) => { if (response.status() >= 400) errors.responses.push(`${response.status()} ${response.url()}`); });
});

test.afterEach(async ({ page }) => {
  const errors = runtimeErrors.get(page);
  expect(errors?.console ?? []).toEqual([]);
  expect(errors?.page ?? []).toEqual([]);
  expect(errors?.requests ?? []).toEqual([]);
  expect(errors?.responses ?? []).toEqual([]);
});

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
    documents: [],
    messageRequests: 0,
    previewPaths: [],
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
    if (url.pathname === "/api/models") return json(route, {
      default_model: "inetcloud-knowledge", gemini_fallback_enabled: true,
      models: [
        { id: "inetcloud-knowledge", label: "iNetCloud Knowledge", provider: "inetcloud", configured: true },
        { id: "gemini", label: "Gemini", provider: "gemini", configured: true },
      ],
    });
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
      const question = String(request.postDataJSON().message);
      const requestedModel = request.postDataJSON().model_id ?? state.modelId;
      state.messageModels.push(requestedModel);
      state.modelId = requestedModel;
      const response = {
        ...responseFor(question), requested_model: requestedModel,
        used_model: state.fallbackNext ? "gemini" : requestedModel,
        fallback_used: state.fallbackNext,
        fallback_reason: state.fallbackNext ? "primary_provider_unavailable" : null,
      };
      state.fallbackNext = false;
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
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
}

test("responsive shell, drawer and composer keyboard behavior", async ({ page }, testInfo: TestInfo) => {
  await installApi(page);
  await openApp(page);
  await expect(page.getByText("Khám phá dữ liệu, phân tích kinh doanh và tra cứu thông tin bằng AI.")).toBeVisible();
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
  await input.press("Shift+Enter");
  await input.type("Dòng hai");
  await expect(input).toHaveValue("Dòng một\nDòng hai");
  await page.screenshot({ path: testInfo.outputPath("input-multiline.png"), fullPage: true });

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
  await expect(page.getByText("Ngoài phạm vi", { exact: true })).toBeVisible();
  await expect(page.getByRole("group", { name: "Bằng chứng hỗ trợ" })).toHaveCount(0);
  await expectNoPageOverflow(page);
});

test("selects models, preserves attribution and restores a fallback conversation", async ({ page }, testInfo) => {
  const state = await installApi(page);
  await openApp(page);
  const selector = page.getByLabel("Chọn mô hình AI");
  await expect(selector).toHaveValue("inetcloud-knowledge");
  await selector.focus();
  await expect(selector).toBeFocused();
  await page.keyboard.press("Escape");
  await selector.selectOption("gemini");
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Top sản phẩm");
  await input.press("Enter");
  await expect(page.locator(".model-attribution").last()).toHaveText("Gemini");
  expect(state.messageModels).toEqual(["gemini"]);
  await selector.selectOption("inetcloud-knowledge");
  await expect.poll(() => state.modelId).toBe("inetcloud-knowledge");
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

test("previews and imports a CSV before selecting the uploaded dataset", async ({ page }) => {
  const state = await installApi(page);
  await openApp(page);
  await openSidebar(page);
  await page.getByRole("button", { name: "Nạp dữ liệu mới" }).click();
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
