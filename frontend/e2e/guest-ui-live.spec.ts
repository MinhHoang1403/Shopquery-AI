import { expect, test } from "@playwright/test";

const runtimeEnv = (
  globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }
).process?.env ?? {};

test.use({ storageState: { cookies: [], origins: [] } });

test("live guest keeps header login and uploads without a duplicate sidebar login", async ({ page }, info) => {
  test.skip(runtimeEnv.SHOPQUERY_LIVE_UI !== "1", "Explicit local UI acceptance opt-in required");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
  const login = page.locator(".chat-header").getByRole("button", { name: "Đăng nhập", exact: true });
  await expect(login).toBeVisible();
  await expect(page.getByRole("button", { name: "Đăng nhập", exact: true })).toHaveCount(1);
  await expect(page.locator(".sidebar-footer").getByRole("button", { name: "Đăng nhập", exact: true })).toHaveCount(0);
  await expect(page.getByText("Đăng nhập để lưu lịch sử và bộ dữ liệu.", { exact: true })).toHaveCount(0);
  const mobileMenu = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
  const mobile = await mobileMenu.isVisible();
  if (mobile) await mobileMenu.click();
  else await page.getByRole("button", { name: "Thu gọn sidebar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tệp tạm thời", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("live-guest-sidebar.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Tệp tạm thời", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Tệp tạm của phiên khách" })).toBeVisible();
  await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
  await login.click();
  await expect(page.getByRole("link", { name: "Tiếp tục với Google" })).toHaveAttribute("href", "/api/auth/login");
  await page.screenshot({ path: info.outputPath("live-header-login.png"), animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
