import { expect, test } from "@playwright/test";

const runtimeEnv = (globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
}).process?.env ?? {};

test("completes SQL, RAG, and Hybrid through the React UI", async ({ page }, testInfo) => {
  test.skip(runtimeEnv.RUN_LIVE_CHAT_E2E !== "1", "Live AI requires explicit opt-in.");
  test.skip(!runtimeEnv.SHOPQUERY_LIVE_STORAGE_STATE, "An authenticated test account is required.");
  test.skip(testInfo.project.name !== "desktop-1440", "Live Gemini smoke runs once on desktop Chromium.");
  test.setTimeout(900_000);

  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const failedResponses: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()}`));
  page.on("response", (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });

  await page.goto("/");
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await page.getByLabel("Chọn mô hình AI").selectOption("gemini");
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");

  const questions = [
    {
      message: "Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?",
      route: "SQL",
      validate: async () => {
        const response = page.locator(".message--assistant").last();
        const table = response.getByRole("region", { name: "Kết quả truy vấn" });
        await expect(table).toHaveCount(0);
        await response.getByRole("button", { name: /Xem bảng dữ liệu/ }).click();
        await expect(table).toBeVisible();
      },
    },
    {
      message: "Chính sách đổi trả của cửa hàng như thế nào?",
      route: "RAG",
      validate: async () => {
        const response = page.locator(".message--assistant").last();
        await expect(response.getByLabel("Nguồn tham khảo")).toHaveCount(0);
        await response.getByRole("button", { name: /Nguồn/ }).click();
        await expect(response.getByLabel("Nguồn tham khảo")).toBeVisible();
      },
    },
    {
      message: "Top 5 sản phẩm bán chạy nhất có thuộc danh mục được miễn phí vận chuyển không?",
      route: "HYBRID",
      validate: async () => {
        const response = page.locator(".message--assistant").last();
        const table = response.getByRole("region", { name: "Kết quả truy vấn" });
        await expect(table).toHaveCount(0);
        await response.getByRole("button", { name: /Xem bảng dữ liệu/ }).click();
        await expect(table).toBeVisible();
        await response.getByRole("button", { name: /Nguồn/ }).click();
        await expect(table).toHaveCount(0);
        await expect(response.getByLabel("Nguồn tham khảo")).toBeVisible();
      },
    },
  ] as const;

  for (const question of questions) {
    await input.fill(question.message);
    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/messages") && response.request().method() === "POST",
      { timeout: 320_000 },
    );
    await input.press("Enter");
    await expect(page.getByLabel("ShopQuery AI đang xử lý")).toBeVisible();
    const apiResponse = await responsePromise;
    expect(apiResponse.status()).toBe(200);
    const body = await apiResponse.json();
    const chatResponse = body.assistant_message.response;
    expect(chatResponse.error).toBeNull();
    expect(chatResponse.route).toBe(question.route);
    const badgeText = question.route === "RAG"
      ? "Tài liệu"
      : question.route === "HYBRID"
        ? "Dữ liệu và tài liệu"
        : "Dữ liệu";
    await expect(page.locator(".route-badge").last()).toHaveText(badgeText, { timeout: 10_000 });
    await question.validate();
  }

  await page.screenshot({ path: testInfo.outputPath("live-conversation.png"), fullPage: true });
  await expect(page.locator(".conversation")).toBeVisible();
  await expect(input).toBeInViewport();
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  expect(failedResponses).toEqual([]);
});
