import { expect, test, type Page } from "@playwright/test";

const runtimeEnv = (
  globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  }
).process?.env ?? {};
async function sendQuestion(page: Page, message: string, expectedRoute: string) {
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await input.fill(message);
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/messages") && response.request().method() === "POST",
    { timeout: 320_000 },
  );
  await input.press("Enter");
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body = await response.json();
  const chat = body.assistant_message.response;
  expect(chat.error).toBeNull();
  expect(chat.route).toBe(expectedRoute);
  return chat;
}

test("creates a multi-source workspace and completes SQL, RAG and Hybrid", async ({ page }) => {
  test.skip(
    runtimeEnv.SHOPQUERY_LIVE_WORKSPACE !== "1",
    "Set SHOPQUERY_LIVE_WORKSPACE=1 with the isolated API running.",
  );
  test.setTimeout(1_200_000);

  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await page.getByRole("button", { name: "Quản lý dữ liệu" }).click();

  const workspaceName = `Workspace browser ${Date.now()}`;
  await page.getByLabel("Tên bộ dữ liệu").fill(workspaceName);
  await page.getByRole("button", { name: "Tạo workspace rỗng" }).click();
  await expect(page.getByText("0 bảng · 0 tài liệu")).toBeVisible();

  const tableInput = page.getByLabel(/Thêm CSV hoặc XLSX/);
  await tableInput.setInputFiles("e2e/fixtures/orders.csv");
  await expect(page.locator(".preview-stats span").filter({ hasText: "3 dòng" })).toBeVisible();
  await page.getByRole("button", { name: "Thêm bảng" }).click();
  await expect(page.getByText("orders.csv · 3 dòng")).toBeVisible();

  await tableInput.setInputFiles("e2e/fixtures/inventory.xlsx");
  const sheetSelect = page.getByLabel("Sheet");
  await expect(sheetSelect).toBeVisible();
  await sheetSelect.selectOption("Tồn kho");
  await expect(page.getByText("LT-01")).toBeVisible();
  await page.getByRole("button", { name: "Thêm bảng" }).click();
  await expect(page.getByText("inventory.xlsx · 3 dòng")).toBeVisible();

  const documentInput = page.getByLabel(/Thêm PDF, DOCX, TXT hoặc MD/);
  for (const filename of ["policy.pdf", "policy.docx", "policy.txt", "policy.md"]) {
    await documentInput.setInputFiles(`e2e/fixtures/${filename}`);
    await expect(page.getByText(filename, { exact: true })).toBeVisible({ timeout: 180_000 });
  }
  await expect(page.getByText("2 bảng · 4 tài liệu")).toBeVisible();
  await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
  await expect(page.getByRole("button", { name: new RegExp(`Chọn bộ dữ liệu.*${workspaceName}`) })).toBeVisible();

  const sql = await sendQuestion(
    page,
    "Top 2 sản phẩm có giá trị đơn hàng cao nhất là gì?",
    "SQL",
  );
  expect(sql.rows).toHaveLength(2);
  expect(sql.sources).toHaveLength(0);

  const rag = await sendQuestion(
    page,
    "Điều kiện miễn phí vận chuyển trong tài liệu là gì?",
    "RAG",
  );
  expect(rag.rows).toHaveLength(0);
  expect(rag.sources.length).toBeGreaterThan(0);
  expect(rag.sources.every((source: { source_file: string }) => source.source_file === "policy.md")).toBe(true);

  const hybrid = await sendQuestion(
    page,
    "Những sản phẩm nào có giá trị đơn hàng đáp ứng điều kiện miễn phí vận chuyển?",
    "HYBRID",
  );
  expect(hybrid.rows.length).toBeGreaterThan(0);
  expect(hybrid.sources.length).toBeGreaterThan(0);
  expect(hybrid.sources.every((source: { source_file: string }) => source.source_file === "policy.md")).toBe(true);

  await page.reload();
  await expect(page.getByText(hybrid.answer)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: new RegExp(`Chọn bộ dữ liệu.*${workspaceName}`) })).toBeVisible();
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
