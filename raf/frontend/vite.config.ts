import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 开发模式下代理到后端（8081）
    proxy: {
      "/api": "http://localhost:8081",
    },
  },
});
