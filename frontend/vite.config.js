import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// ส่งต่อคำขอ /api ไปยังหลังบ้าน FastAPI ที่พอร์ต 8000
// ใน Docker ตั้ง API_PROXY_TARGET เป็นชื่อ service ของหลังบ้าน (ดู docker-compose.yml)
const apiTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": apiTarget } },
});
