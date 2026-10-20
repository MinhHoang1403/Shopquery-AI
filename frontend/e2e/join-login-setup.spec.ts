import { expect, test } from "@playwright/test";

const env = (globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
}).process?.env ?? {};

test.use({ storageState: { cookies: [], origins: [] }, trace: "off", screenshot: "off", video: "off" });

test("manual Google login readiness without exporting session state", async ({ page }) => {
  test.skip(env.SHOPQUERY_JOIN_MANUAL_LOGIN !== "1", "Manual login opt-in required");
  test.setTimeout(600_000);
  await page.goto("http://127.0.0.1:8080/");
  await expect(page.getByRole("button", { name: "Mở menu tài khoản" })).toBeAttached({ timeout: 570_000 });
});
