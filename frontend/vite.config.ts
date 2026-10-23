import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const containerDev = env.SHOPQUERY_DEV_CONTAINER === "1";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      watch: containerDev ? { usePolling: true, interval: 1000 } : undefined,
      proxy: env.SHOPQUERY_E2E_START_SERVER === "1" ? undefined : {
        "/api": {
          target: env.SHOPQUERY_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
          changeOrigin: true,
          configure(proxy) {
            proxy.on("proxyReq", (proxyRequest, request) => {
              const peer = request.socket.remoteAddress ?? "unknown";
              proxyRequest.setHeader("X-Forwarded-For", peer);
              proxyRequest.setHeader("X-Real-IP", peer);
              proxyRequest.setHeader("X-Forwarded-Proto", "http");
            });
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      exclude: ["e2e/**", "node_modules/**", "dist/**"],
    },
  };
});
