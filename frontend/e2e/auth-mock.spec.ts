import { expect, test } from "@playwright/test";

test("guest sees login only and does not request private workspace data", async ({ page }) => {
  const paths: string[] = [];
  await page.route("**/api/**", async (route) => {
    paths.push(new URL(route.request().url()).pathname);
    await route.fulfill({ status: 401, json: { detail: "Login required" } });
  });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Tiếp tục với Google" })).toHaveAttribute("href", "/api/auth/login");
  await expect(page.getByLabel("Nhập câu hỏi cho ShopQuery AI")).toHaveCount(0);
  expect([...new Set(paths)]).toEqual(["/api/auth/me"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("logout clears account A and a new session starts with account B", async ({ page }) => {
  let account = "A";
  let authenticated = true;
  let csrfAtLogout: string | undefined;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
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
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(page.getByRole("link", { name: "Tiếp tục với Google" })).toBeVisible();
  await expect.poll(() => csrfAtLogout).toBe("csrf-A");
  await expect(page.getByText("Account A", { exact: true })).toHaveCount(0);
  account = "B";
  authenticated = true;
  await page.reload();
  await expect(page.getByRole("status", { name: "API sẵn sàng" })).toBeVisible();
  if (await menu.isVisible()) await menu.click();
  await expect(page.getByText("Account B", { exact: true })).toBeVisible();
  await expect(page.getByText("Account A", { exact: true })).toHaveCount(0);
});
