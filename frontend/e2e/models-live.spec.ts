import { expect, test } from "@playwright/test";

const runtimeEnv = (globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
}).process?.env ?? {};

test("uses manual Gemini then Knowledge and restores per-answer attribution", async ({ page }, testInfo) => {
  test.skip(runtimeEnv.SHOPQUERY_LIVE_MODELS !== "1", "Opt-in live test on an isolated API.");
  test.skip(!runtimeEnv.SHOPQUERY_LIVE_STORAGE_STATE, "An authenticated test account is required.");
  test.setTimeout(600_000);
  await expect.poll(async () => (await page.request.get("/api/health")).status(), {
    timeout: 30_000,
  }).toBe(200);
  await page.goto("/");
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  const selector = page.getByLabel("Chọn mô hình AI");
  await expect(selector).toHaveValue("inetcloud-knowledge");
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  for (const question of [
    { model: "gemini", message: "Có tổng cộng bao nhiêu sản phẩm trong bảng products?", route: "SQL" },
    { model: "inetcloud-knowledge", message: "Khách hàng có bao nhiêu ngày để yêu cầu đổi trả?", route: "RAG" },
  ]) {
    await selector.selectOption(question.model);
    await expect(selector).toBeEnabled();
    await input.fill(question.message);
    const sent = page.waitForResponse((response) => response.url().endsWith("/messages") && response.request().method() === "POST", { timeout: 320_000 });
    await input.press("Enter");
    const response = await sent;
    expect(response.request().postDataJSON().model_id).toBe(question.model);
    const chat = (await response.json()).assistant_message.response;
    expect(chat.error).toBeNull();
    expect(chat.requested_model).toBe(question.model);
    expect(chat.used_model).toBe(question.model);
    expect(chat.fallback_used).toBe(false);
    expect(chat.route).toBe(question.route);
  }
  await page.reload();
  await expect(selector).toHaveValue("inetcloud-knowledge");
  await expect(page.locator(".model-attribution")).toHaveText(["Gemini", "iNetCloud Knowledge"]);
  await page.screenshot({ path: testInfo.outputPath("model-selection-live.png"), fullPage: true });
});
