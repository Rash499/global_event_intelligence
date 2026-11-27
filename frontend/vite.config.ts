/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind all interfaces so the sandbox preview proxy can reach the dev server.
    host: "0.0.0.0",
    port: Number(process.env.PORT) || 5173,
    strictPort: false,
    // Preview hosts are proxied under a dynamic domain, so the allowlist is
    // permissive here. Production builds are served statically and do not use
    // the dev server.
    allowedHosts: true,
    proxy: {
      // The app calls relative /api URLs; Vite forwards them to FastAPI. This
      // keeps the browser from ever calling localhost directly, which would
      // break inside the preview environment.
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        ws: false,
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: Number(process.env.PORT) || 4173,
    allowedHosts: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Keep the heavy 3D stack out of the app chunk so it can cache independently.
        manualChunks: {
          three: ["three"],
          globe: ["globe.gl"],
          react: ["react", "react-dom"],
        },
      },
    },
    // The globe bundle is legitimately large; the warning is noise.
    chunkSizeWarningLimit: 1300,
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{js,jsx,ts,tsx}"],
    coverage: {
      provider: "v8",
      include: [
        "src/hooks/**",
        "src/navigation/**",
        "src/components/ui/**",
        "src/components/Navbar.jsx",
        "src/components/StatsBar.jsx",
        "src/components/EventList.jsx",
        "src/components/CategoryFilter.jsx",
        "src/components/AlertToast.jsx",
        "src/components/workspace/**",
        "src/services/format.jsx",
      ],
    },
  },
});
