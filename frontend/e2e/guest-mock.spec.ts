import { expect, test, type Page } from "@playwright/test";
import { guestStatus } from "./guest-fixture";

async function installGuest(page: Page, ai = true) {
  let status = guestStatus(ai);
  let sessions = 0;
  const calls: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    calls.push(url.pathname);
    if (url.pathname === "/api/auth/me") return route.fulfill({ status: 401, json: { detail: "Guest" } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } });
    if (url.pathname === "/api/guest/session") {
      status = guestStatus(ai); sessions++;
      status.token = `offline-${sessions}`;
      return route.fulfill({ json: status });
    }
    if (url.pathname === "/api/guest/reset") return route.fulfill({ status: 204 });
    if (url.pathname.startsWith("/api/guest/files")) {
      const filename = url.searchParams.get("filename")!;
      const document = filename.endsWith(".md");
      const preview = {
        file_id: filename, filename, kind: document ? "document" : "table", size: 30,
        row_count: document ? null : 2, chunk_count: document ? 1 : 0,
        columns: document ? [] : [{ source_name: "Fee", name: "fee", data_type: "BIGINT" }],
        rows: document ? [] : [{ fee: 100 }, { fee: 200 }],
        sheet_names: [], sheet_name: null, warnings: [],
      };
      if (url.pathname === "/api/guest/files") status.files.push(preview);
      return route.fulfill({ json: { preview, status } });
    }
    if (url.pathname === "/api/guest/chat") {
      const body = route.request().postDataJSON();
      expect(Object.keys(body).sort()).toEqual(["message", "model_id"]);
      if (status.remaining === 0) return route.fulfill({ status: 429, json: { detail: "Hết lượt" } });
      status.remaining--;
      const pipeline = body.message === "SQL" ? "SQL" : body.message === "RAG" ? "RAG" : body.message === "HYBRID" ? "HYBRID" : null;
      const sql = pipeline === "SQL" || pipeline === "HYBRID";
      const rag = pipeline === "RAG" || pipeline === "HYBRID";
      return route.fulfill({ json: { status, response: {
        answer: pipeline ? `Kết quả mock ${pipeline}: 300` : `Giải thích mock ${5 - status.remaining}`,
        route: pipeline, sql: sql ? "SELECT SUM(fee) AS total FROM pg_temp.table_1" : null,
        rows: sql ? [{ total: 300 }] : [],
        sources: rag ? [{ chunk_id: 1, source_file: "rules.md", section_title: "Quy định", content: "Ngưỡng là 250." }] : [],
        error: null, requested_model: body.model_id, used_model: body.model_id,
        fallback_used: false, fallback_reason: null,
      } } });
    }
    throw new Error(`Unexpected private API: ${url.pathname}`);
  });
  return { calls, sessions: () => sessions };
}

async function openUploads(page: Page) {
  const menu = page.getByRole("button", { name: "Mở thanh điều hướng" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name: "Tệp tạm thời", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test("guest upload SQL RAG Hybrid use common chat UI and refresh loses files/history", async ({ page }, info) => {
  const mock = await installGuest(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("guest-home.png") });
  await openUploads(page);
  for (const name of ["fees.csv", "rules.md"]) {
    await page.locator("#guest-file").setInputFiles(`e2e/fixtures/${name}`);
    await page.getByRole("button", { name: "Dùng tệp trong phiên này" }).click();
    await expect(page.getByRole("button", { name: "Dùng tệp trong phiên này" })).toHaveCount(0);
  }
  await expect(page.locator(".guest-file-list")).toContainText("fees.csv");
  await expect(page.locator(".guest-file-list")).toContainText("rules.md");
  await page.screenshot({ path: info.outputPath("guest-upload.png") });
  await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
  for (const pipeline of ["SQL", "RAG", "HYBRID"]) {
    await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").fill(pipeline);
    await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").press("Enter");
    await expect(page.getByText(`Kết quả mock ${pipeline}: 300`, { exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Nguồn · 1", exact: true }).last().click();
  await expect(page.getByText("rules.md", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("guest-chat.png") });
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
  await expect(page.getByText("Kết quả mock HYBRID: 300", { exact: true })).toHaveCount(0);
  await openUploads(page);
  await expect(page.locator(".guest-file-list li")).toHaveCount(0);
  expect(mock.sessions()).toBe(2);
  expect(mock.calls.every((path) => path === "/api/auth/me" || path === "/api/health" || path.startsWith("/api/guest/"))).toBe(true);
});

test("guest quota blocks sending but preserves editing, visible chats and optional login", async ({ page }, info) => {
  await installGuest(page);
  await page.goto("/");
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  for (let i = 1; i <= 5; i++) {
    await input.fill(`Giải thích ${i}`); await input.press("Enter");
    await expect(page.getByText(`Giải thích mock ${i}`, { exact: true })).toBeVisible();
  }
  await expect(input).toBeEditable();
  await input.fill("Câu hỏi giữ lại sau quota");
  await expect(page.getByRole("button", { name: "Gửi câu hỏi" })).toHaveAttribute("aria-disabled", "true");
  await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText("Đã hết lượt hỏi");
  await expect(input).toHaveValue("Câu hỏi giữ lại sau quota");
  await expect(page.getByText("Giải thích mock 1", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("guest-limit.png") });
  await page.getByRole("button", { name: "Đăng nhập để tiếp tục", exact: true }).click();
  await expect(page.getByRole("link", { name: "Tiếp tục với Google" })).toHaveAttribute("href", "/api/auth/login");
  await page.keyboard.press("Escape");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("provider gate off permits guest upload but no generation and a new tab is independent", async ({ page, context }) => {
  const mock = await installGuest(page, false);
  await page.goto("/");
  const input = page.getByLabel("Nhập câu hỏi cho ShopQuery AI");
  await expect(input).toBeEditable();
  await input.fill("Câu hỏi chưa gửi");
  await input.press("Shift+Enter");
  await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText("AI đang tạm chưa được bật");
  expect(mock.calls).not.toContain("/api/guest/chat");
  await expect(page.getByText("AI dùng thử chưa được bật.", { exact: false })).toBeVisible();
  await openUploads(page);
  await page.locator("#guest-file").setInputFiles("e2e/fixtures/fees.csv");
  await page.getByRole("button", { name: "Dùng tệp trong phiên này" }).click();
  await expect(page.locator(".guest-file-list li")).toHaveCount(1);
  await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await test.step("a second tab starts without the first tab's temporary files", async () => {
    const second = await context.newPage();
    await installGuest(second, false); await second.goto("/");
    await openUploads(second);
    await expect(second.locator(".guest-file-list li")).toHaveCount(0);
  });
});
