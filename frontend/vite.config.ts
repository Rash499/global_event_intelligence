/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{js,jsx,ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/hooks/**", "src/navigation/**", "src/components/ui/**", "src/components/Navbar.jsx", "src/components/StatsBar.jsx", "src/components/EventList.jsx", "src/components/CategoryFilter.jsx", "src/components/AlertToast.jsx"],
    },
  },
});
