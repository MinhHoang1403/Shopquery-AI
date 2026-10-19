import { defineConfig } from "@playwright/test";

const runtimeEnv = (
  globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  }
).process?.env ?? {};

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  reporter: "line",
  webServer: runtimeEnv.SHOPQUERY_E2E_START_SERVER === "1" ? {
    command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
    url: "http://127.0.0.1:5173", reuseExistingServer: false,
  } : undefined,
  use: {
    storageState: runtimeEnv.SHOPQUERY_LIVE_STORAGE_STATE || undefined,
    baseURL: runtimeEnv.SHOPQUERY_E2E_BASE_URL ?? "http://127.0.0.1:8080",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop-1440",
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: "desktop-1280",
      use: { viewport: { width: 1280, height: 800 } },
    },
    {
      name: "tablet-768",
      use: { viewport: { width: 768, height: 1024 } },
    },
    {
      name: "mobile-390",
      use: {
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
      },
    },
    {
      name: "mobile-320",
      use: {
        viewport: { width: 320, height: 700 },
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
});
