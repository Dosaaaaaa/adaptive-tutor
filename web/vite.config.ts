import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `npm run dev` serves the app on :5173 and forwards /api to the Python server on :8080.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8080" } },
  build: { outDir: "dist", target: "es2022", sourcemap: false, chunkSizeWarningLimit: 320 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
