import { expect, test, type Page } from "@playwright/test";

const runtimeEnv = (
  globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }
).process?.env ?? {};

test.use({ storageState: { cookies: [], origins: [] } });

async function selectCsv(page: Page, name: string, content: string) {
  await page.locator("#guest-file").evaluate((input: HTMLInputElement, file) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([file.content], file.name, { type: "text/csv" }));
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, { name, content });
}

test("real guest preview keeps decimal digits and rejects mixed timezone inputs", async ({ page }, info) => {
  test.skip(runtimeEnv.SHOPQUERY_LIVE_SQL_CONTRACT !== "1", "Explicit synthetic local acceptance opt-in required");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
  await page.getByRole("button", { name: "Thêm dữ liệu", exact: true }).click();
  const content = "Instant,Amount\n2026-10-01T00:30:00+07:00,12345678901234567890.12\n";
  const previewResponse = page.waitForResponse((response) => response.url().includes("/api/guest/files/preview"));
  await selectCsv(page, "correctness-synthetic.csv", content);
  const preview = await previewResponse;
  expect(preview.status()).toBe(200);
  const body = await preview.json();
  expect(body.preview.columns.map((column: { data_type: string }) => column.data_type)).toEqual(["TIMESTAMPTZ", "NUMERIC"]);
  await expect(page.getByRole("cell", { name: "12345678901234567890.12", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("decimal-timestamp-preview.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Dùng tệp trong phiên này" }).click();
  await expect(page.locator(".guest-file-list")).toContainText("correctness-synthetic.csv");
  const invalidResponse = page.waitForResponse((response) => response.url().includes("/api/guest/files/preview"));
  await selectCsv(page, "mixed-synthetic.csv", "Instant\n2026-10-01T00:30:00+07:00\n2026-10-01T00:30:00\n");
  expect((await invalidResponse).status()).toBe(422);
  await expect(page.getByRole("alert")).toContainText("trộn");
  await expect(page.getByRole("button", { name: "Dùng tệp trong phiên này" })).toHaveCount(0);
  await expect(page.locator(".guest-file-list li")).toHaveCount(1);
});
