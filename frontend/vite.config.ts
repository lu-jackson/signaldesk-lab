import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 開發期：前端 5173，/api 與 /t 轉到後端 8000（同源，不需要 CORS）。
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/t": "http://127.0.0.1:8000",
      "/demo-landing": "http://127.0.0.1:8000",
    },
  },
});
