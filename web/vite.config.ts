import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the browser calls /api on the Vite origin and Vite forwards to the backend,
// so there is no CORS or mixed-content problem. Override with VITE_API_TARGET.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://144.202.28.129:8000";
  return {
    plugins: [react()],
    server: { port: 5173, proxy: { "/api": { target, changeOrigin: true, timeout: 180000, proxyTimeout: 180000 } } },
  };
});
