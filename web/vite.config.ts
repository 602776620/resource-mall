import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// dev proxy → 后端 127.0.0.1:8000（07 §1 / 08 §3）。
// 真实业务 API 在 /api/v1 下；/health 为基础设施探活端点（不在 v1 前缀），
// 一并转发以便 :5173 侧验证代理链路（T02 验收）。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
