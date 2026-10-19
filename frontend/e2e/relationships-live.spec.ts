import { expect, test } from "@playwright/test";

const runtimeEnv = (
  globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }
).process?.env ?? {};

test.use({ storageState: { cookies: [], origins: [] }, trace: "off", screenshot: "off", video: "off" });

test("live local guest relationship lifecycle and capability security without AI", async ({ page, request }, info) => {
  test.skip(runtimeEnv.SHOPQUERY_JOIN_LIVE_UI !== "1", "Explicit local acceptance opt-in required");
  expect(new URL(info.project.use.baseURL as string).origin).toBe("http://127.0.0.1:8080");
  const sessionResponse = page.waitForResponse((response) => response.url().endsWith("/api/guest/session") && response.request().method() === "POST");
  await page.goto("/");
  const session = await (await sessionResponse).json();
  expect(session.sql_join_v1_enabled).toBe(true);
  const headers = { Origin: "http://127.0.0.1:8080", "X-Guest-Token": session.token, "X-Guest-CSRF": session.csrf_token };
  const open = async () => {
    const menu = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
    if (await menu.isVisible()) await menu.click();
    await page.getByRole("button", { name: "Tệp tạm thời", exact: true }).click();
  };
  await open();
  for (const [name, content] of [
    ["students.csv", "Id,Name\n101,An\n102,Binh\n"],
    ["payments.csv", "Id,Student id,Amount\n1,101,20.00\n2,101,30.00\n3,102,0.00\n"],
  ]) {
    await page.locator("#guest-file").evaluate((node, file) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([file.content], file.name, { type: "text/csv" }));
      (node as HTMLInputElement).files = transfer.files;
      node.dispatchEvent(new Event("change", { bubbles: true }));
    }, { name, content });
    await page.getByRole("button", { name: "Dùng tệp trong phiên này", exact: true }).click();
    await expect(page.locator(".guest-file-list")).toContainText(name);
  }
  await page.getByText("Liên kết bảng", { exact: true }).click();
  await page.getByLabel("Bảng chi tiết (fact)").selectOption({ label: "payments.csv" });
  await page.getByLabel("Khóa ở bảng chi tiết").selectOption("student_id");
  await page.getByLabel("Bảng danh mục (dimension)").selectOption({ label: "students.csv" });
  await page.getByLabel("Khóa ở bảng danh mục").selectOption("id");
  const previewResponse = page.waitForResponse((response) => response.url().endsWith("/api/guest/relationships/preview"));
  await page.getByRole("button", { name: "Kiểm tra quan hệ", exact: true }).click();
  const preview = await (await previewResponse).json();
  expect(preview.valid).toBe(true);
  expect([preview.source_rows, preview.target_rows, preview.orphan_rows]).toEqual([3, 2, 0]);
  await expect(page.getByRole("region", { name: "Kết quả kiểm tra quan hệ" })).toContainText("chưa được kích hoạt");
  const confirmResponse = page.waitForResponse((response) => response.url().endsWith("/api/guest/relationships") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Xác nhận liên kết", exact: true }).click();
  const relation = await (await confirmResponse).json();
  const remove = page.getByRole("button", { name: "Xóa liên kết payments.csv đến students.csv", exact: true });
  await expect(remove).toBeVisible();
  const foreign = await request.post("/api/guest/session", { headers: { Origin: headers.Origin }, data: {} });
  expect(foreign.ok()).toBe(true);
  const other = await foreign.json();
  const otherHeaders = { Origin: headers.Origin, "X-Guest-Token": other.token, "X-Guest-CSRF": other.csrf_token };
  expect((await request.get("/api/guest/relationships", { headers: otherHeaders })).ok()).toBe(true);
  expect((await (await request.get("/api/guest/relationships", { headers: otherHeaders })).json()).relationships).toEqual([]);
  expect((await request.delete(`/api/guest/relationships/${relation.relationship_id}?confirmed=true`, { headers: otherHeaders })).status()).toBe(404);
  expect((await request.post("/api/guest/relationships/preview", { headers: otherHeaders, data: preview })).status()).toBe(422);
  const selection = { source_table_id: preview.source_table_id, source_column: preview.source_column, target_table_id: preview.target_table_id, target_column: preview.target_column };
  expect((await request.post("/api/guest/relationships/preview", { headers: otherHeaders, data: selection })).status()).toBe(404);
  expect((await request.post("/api/guest/relationships/preview", { headers: { ...headers, "X-Guest-CSRF": "invalid" }, data: selection })).status()).toBe(403);
  expect((await request.post("/api/guest/relationships/preview", { headers: { ...headers, Origin: "https://invalid.example" }, data: selection })).status()).toBe(403);
  expect((await request.get("/api/datasets")).status()).toBe(401);
  expect((await request.get("/api/auth/me")).status()).toBe(401);
  expect(await page.locator(".relationship-panel").evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("live-guest-join.png") });
  await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
  await open();
  await page.getByText("Liên kết bảng", { exact: true }).click();
  await remove.click();
  await page.getByRole("button", { name: "Xác nhận xóa liên kết", exact: true }).click();
  await expect(page.getByText("Chưa có liên kết đã xác nhận.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Bảng chi tiết (fact)").locator("option")).toHaveCount(3);
  expect((await (await request.get("/api/guest/limits", { headers })).json()).files).toHaveLength(2);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  expect((await request.post("/api/guest/reset", { headers: otherHeaders, data: {} })).status()).toBe(204);
  expect((await request.post("/api/guest/reset", { headers, data: {} })).status()).toBe(204);
});
