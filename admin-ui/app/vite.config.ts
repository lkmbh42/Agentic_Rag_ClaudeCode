import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build to static assets served by nginx (admin-ui container).
// Dev server proxies /api -> backend so dev is same-origin too, matching the
// container. This is what makes the httpOnly refresh cookie work in dev.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
