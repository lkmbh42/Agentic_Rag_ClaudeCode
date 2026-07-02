import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build to static assets served by nginx (admin-ui container).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
});
