import { expect, test } from "@playwright/test";
import { guestStatus } from "./guest-fixture";

test("guest sees chat and optional login without private workspace requests", async ({ page }) => {
  const paths: string[] = [];
  await page.route("**/api/**", async (route) => {
    paths.push(new URL(route.request().url()).pathname);
    if (route.request().url().includes("/api/guest/")) return route.fulfill({ json: guestStatus() });
    if (route.request().url().includes("/api/health")) return route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } });
    await route.fulfill({ status: 401, json: { detail: "Login required" } });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
  await expect(page.getByLabel("Nhập câu hỏi cho ShopQuery AI")).toBeEditable();
  await page.locator(".chat-header").getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page.getByRole("link", { name: "Tiếp tục với Google" })).toHaveAttribute("href", "/api/auth/login");
  const google = page.getByRole("link", { name: "Tiếp tục với Google" });
  expect(await google.evaluate((node) => getComputedStyle(node).textDecorationLine)).toBe("none");
  expect((await google.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press("Tab");
  await expect(google).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Tiếp tục dùng thử" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("dialog").getByRole("button", { name: "Đóng", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(paths.every((path) => path === "/api/auth/me" || path === "/api/health" || path.startsWith("/api/guest/"))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("clean welcome and long account menu fit the viewport including collapsed sidebar", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: {
      user: { user_id: "synthetic", display_name: "Người kiểm thử với tên hiển thị rất dài trên thiết bị di động", email: "very.long.synthetic.account.name.for.layout@example.invalid" },
      csrf_token: "offline-csrf",
    } });
    if (path === "/api/health") return route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } });
    if (path === "/api/models") return route.fulfill({ json: {
      default_model: "inetcloud-knowledge", gemini_fallback_enabled: false,
      models: [{ id: "inetcloud-knowledge", label: "Knowledge", provider: "inetcloud", configured: true }],
    } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Không gian dữ liệu của bạn" })).toBeVisible();
  await expect(page.getByLabel("Nhập câu hỏi cho ShopQuery AI")).toBeEditable();
  await expect(page.getByText("Phân tích bán hàng", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("empty-welcome.png") });
  const mobileMenu = page.getByRole("button", { name: "Mở thanh điều hướng" });
  if (await mobileMenu.isVisible()) await mobileMenu.click();
  const account = page.getByRole("button", { name: "Mở menu tài khoản" });
  await account.click();
  const popup = page.getByRole("menu", { name: "Tài khoản", exact: true });
  await expect(popup).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Đăng xuất" })).toBeFocused();
  const box = await popup.boundingBox();
  expect(box).not.toBeNull();
  const viewport = page.viewportSize()!;
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
  await page.screenshot({ path: testInfo.outputPath("account-menu.png") });
  await page.keyboard.press("Escape");
  await expect(popup).toHaveCount(0);
  await expect(account).toBeFocused();
  await account.click();
  await page.getByRole("button", { name: "Đoạn chat mới" }).click();
  await expect(popup).toHaveCount(0);
  const collapse = page.getByRole("button", { name: "Thu gọn sidebar" });
  if (await collapse.isVisible()) {
    await collapse.click();
    await account.click();
    await expect(popup).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("collapsed-account.png") });
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("authentication loading does not flash private application or login", async ({ page }, testInfo) => {
  await page.route("**/api/guest/**", (route) => route.fulfill({ json: guestStatus() }));
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } }));
  let release: () => void = () => undefined;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/auth/me", async (route) => {
    await pending;
    await route.fulfill({ status: 401, json: { detail: "Login required" } });
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Đang kiểm tra phiên đăng nhập…");
  await expect(page.getByRole("link", { name: "Tiếp tục với Google" })).toHaveCount(0);
  await expect(page.getByLabel("Nhập câu hỏi cho ShopQuery AI")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("auth-loading.png") });
  release();
  await expect(page.locator(".chat-header").getByRole("button", { name: "Đăng nhập", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("guest-login.png") });
});

test("logout clears account A and a new session starts with account B", async ({ page }, testInfo) => {
  let account = "A";
  let authenticated = true;
  let csrfAtLogout: string | undefined;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith("/api/guest/")) return route.fulfill({ json: guestStatus() });
    if (path === "/api/auth/me") return route.fulfill({ status: authenticated ? 200 : 401, json: {
      user: { user_id: account, email: `${account}@example.invalid`, display_name: `Account ${account}` },
      csrf_token: `csrf-${account}`,
    } });
    if (path === "/api/auth/logout") {
      csrfAtLogout = route.request().headers()["x-csrf-token"];
      authenticated = false;
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/health") return route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } });
    if (path === "/api/models") return route.fulfill({ json: {
      default_model: "inetcloud-knowledge", gemini_fallback_enabled: false,
      models: [{ id: "inetcloud-knowledge", label: "Knowledge", provider: "inetcloud", configured: true }],
    } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
  const menu = page.getByRole("button", { name: "Mở thanh điều hướng" });
  if (await menu.isVisible()) await menu.click();
  await expect(page.getByText("Account A", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Mở menu tài khoản" }).click();
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await expect(page.locator(".chat-header").getByRole("button", { name: "Đăng nhập", exact: true })).toBeVisible();
  await expect.poll(() => csrfAtLogout).toBe("csrf-A");
  await expect(page.getByText("Account A", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("logged-out-guest.png") });
  account = "B";
  authenticated = true;
  await page.reload();
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
  if (await menu.isVisible()) await menu.click();
  await expect(page.getByText("Account B", { exact: true })).toBeVisible();
  await expect(page.getByText("Account A", { exact: true })).toHaveCount(0);
});
