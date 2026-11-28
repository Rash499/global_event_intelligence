import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { DEMO_DATA_ENABLED: "true", ENVIRONMENT: "development", DATABASE_URL: "sqlite:///./data/e2e.db", SCHEDULER_ENABLED: "false", RAG_ENABLED: "false" },
    },
    {
      command: "npm run dev -- --host 0.0.0.0 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { VITE_API_PROXY_TARGET: "http://127.0.0.1:8000" },
    },
  ],
});
