import { expect, test, type Page, type TestInfo } from "@playwright/test";

const health = { status: "ok", service: "ShopQuery AI" };

const sqlResponse = {
  answer: "Top 5 sản phẩm bán chạy nhất đã được tổng hợp.",
  route: "SQL",
  sql: "SELECT product_name, category_name, total_quantity FROM sales ORDER BY total_quantity DESC LIMIT 5",
  rows: [
    { product_name: "Điện thoại SQ 010", category_name: "Điện thoại", total_quantity: 15 },
    { product_name: "Thiết bị âm thanh SQ 009", category_name: "Âm thanh", total_quantity: 14 },
    { product_name: "Thiết bị gia dụng SQ 006", category_name: "Gia dụng thông minh", total_quantity: 11 },
  ],
  sources: [],
  error: null,
};

const ragResponse = {
  answer: "Yêu cầu đổi trả cần được gửi trong vòng 14 ngày kể từ ngày nhận hàng.",
  route: "RAG",
  sql: null,
  rows: [],
  sources: [
    {
      chunk_id: 310,
      source_file: "return_policy.md",
      section_title: "Chính sách đổi trả > Thời hạn yêu cầu",
      content: "Yêu cầu đổi trả phải được gửi trong vòng 14 ngày kể từ ngày nhận hàng.",
    },
  ],
  error: null,
};

const hybridResponse = {
  answer: "Laptop SQ 018 thuộc danh mục được miễn phí vận chuyển.",
  route: "HYBRID",
  sql: "SELECT product_name, category_code, total_quantity FROM sales ORDER BY total_quantity DESC LIMIT 5",
  rows: [
    {
      product_name: "Laptop SQ 018 phiên bản cấu hình cao",
      category_code: "LAPTOP",
      total_quantity: 82,
      comparison_status: "Được miễn phí vận chuyển tiêu chuẩn",
    },
  ],
  sources: [
    {
      chunk_id: 315,
      source_file: "shipping_policy.md",
      section_title: "Chính sách vận chuyển > Miễn phí vận chuyển",
      content: "Danh mục laptop được miễn phí vận chuyển tiêu chuẩn.",
    },
  ],
  error: null,
};

async function openWithHealth(page: Page) {
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(health) });
  });
  await page.goto("/");
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
}

async function mockChat(page: Page, body: unknown, status = 200, delayMs = 0) {
  await page.route("**/api/chat", async (route) => {
    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function submitWithEnter(page: Page, question: string) {
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill(question);
  await input.press("Enter");
}

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
}

async function saveLayoutScreenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

test("renders the responsive shell and preserves Shift+Enter", async ({ page }, testInfo) => {
  let chatRequests = 0;
  await page.route("**/api/chat", async (route) => {
    chatRequests += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sqlResponse) });
  });
  await openWithHealth(page);

  await expect(page.getByText("ShopQuery AI", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tìm câu trả lời từ dữ liệu cửa hàng" })).toBeVisible();
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill("Dòng một");
  await input.press("Shift+Enter");
  await input.type("Dòng hai");

  await expect(input).toHaveValue("Dòng một\nDòng hai");
  expect(chatRequests).toBe(0);
  await expectNoPageOverflow(page);
  await saveLayoutScreenshot(page, testInfo, "shell.png");
});

test("sends once, shows loading, and renders collapsible SQL with a scroll-safe table", async ({ page }, testInfo) => {
  let chatRequests = 0;
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(health) });
  });
  await page.route("**/api/chat", async (route) => {
    chatRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 350));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sqlResponse) });
  });
  await page.goto("/");

  await page.getByRole("button", { name: /Phân tích bán hàng/ }).click();
  await expect(page.getByLabel("ShopQuery AI đang xử lý")).toBeVisible();
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await expect(input).toBeDisabled();
  await input.press("Enter");

  await expect(page.getByText(sqlResponse.answer)).toBeVisible();
  expect(chatRequests).toBe(1);
  const sqlPanel = page.locator("details.sql-card");
  await expect(sqlPanel).not.toHaveAttribute("open", "");
  await sqlPanel.locator("summary").click();
  await expect(sqlPanel).toHaveAttribute("open", "");
  await expect(sqlPanel.getByText(/SELECT product_name/)).toBeVisible();
  await sqlPanel.locator("summary").click();
  await expect(sqlPanel).not.toHaveAttribute("open", "");
  await expect(page.getByRole("region", { name: "Kết quả truy vấn" })).toContainText("Điện thoại SQ 010");
  await expectNoPageOverflow(page);
  await saveLayoutScreenshot(page, testInfo, "sql-response.png");
});

test("renders RAG sources", async ({ page }) => {
  await mockChat(page, ragResponse);
  await openWithHealth(page);
  await submitWithEnter(page, "Chính sách đổi trả của cửa hàng như thế nào?");

  await expect(page.getByText(ragResponse.answer)).toBeVisible();
  await expect(page.getByLabel("Nguồn tham khảo")).toContainText("return_policy.md");
  await expect(page.locator("details.sql-card")).toHaveCount(0);
});

test("renders Hybrid SQL, table, and sources without mobile overflow", async ({ page }, testInfo) => {
  await mockChat(page, hybridResponse);
  await openWithHealth(page);
  await submitWithEnter(page, "Top 5 sản phẩm bán chạy nhất có thuộc danh mục được miễn phí vận chuyển không?");

  await expect(page.getByText(hybridResponse.answer)).toBeVisible();
  await expect(page.locator("details.sql-card")).toBeVisible();
  const tableShell = page.getByRole("region", { name: "Kết quả truy vấn" });
  await expect(tableShell).toContainText("Laptop SQ 018");
  await expect(page.getByLabel("Nguồn tham khảo")).toContainText("shipping_policy.md");
  await expectNoPageOverflow(page);
  if (testInfo.project.name === "mobile") {
    const tableDimensions = await tableShell.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(tableDimensions.scrollWidth).toBeGreaterThan(tableDimensions.clientWidth);
  }
  await saveLayoutScreenshot(page, testInfo, "hybrid-response.png");
});

test("renders Unsupported without fabricated evidence", async ({ page }) => {
  await mockChat(page, {
    answer: "ShopQuery AI không hỗ trợ yêu cầu này vì nằm ngoài dữ liệu cửa hàng.",
    route: "UNSUPPORTED",
    sql: null,
    rows: [],
    sources: [],
    error: null,
  });
  await openWithHealth(page);
  await submitWithEnter(page, "Dự báo thời tiết ngày mai?");

  await expect(page.getByText("Ngoài phạm vi")).toBeVisible();
  await expect(page.getByLabel("Nguồn tham khảo")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
});

const errorCases = [
  {
    name: "HTTP 200 business error",
    setup: async (page: Page) => mockChat(page, {
      answer: "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
      route: null,
      sql: null,
      rows: [],
      sources: [],
      error: "gemini_unavailable",
    }),
    message: "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
  },
  {
    name: "HTTP 422",
    setup: async (page: Page) => mockChat(page, { detail: [] }, 422),
    message: "Câu hỏi không hợp lệ. Vui lòng kiểm tra nội dung và độ dài.",
  },
  {
    name: "HTTP 500",
    setup: async (page: Page) => mockChat(page, { error: "internal_error" }, 500),
    message: "Máy chủ gặp sự cố khi xử lý câu hỏi. Vui lòng thử lại sau.",
  },
  {
    name: "network failure",
    setup: async (page: Page) => {
      await page.route("**/api/chat", async (route) => route.abort("connectionfailed"));
    },
    message: "Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.",
  },
] as const;

for (const errorCase of errorCases) {
  test(`shows a recoverable error for ${errorCase.name}`, async ({ page }) => {
    await errorCase.setup(page);
    await openWithHealth(page);
    await submitWithEnter(page, "Một câu hỏi hợp lệ");

    await expect(page.getByText(errorCase.message)).toBeVisible();
    await expect(page.getByText("Không thể xử lý")).toBeVisible();
    await expect(page.getByLabel("Nhập câu hỏi cho ShopQuery AI")).toHaveValue("Một câu hỏi hợp lệ");
  });
}
