import { defineConfig, devices } from "@playwright/test";
const frontendPort = process.env.E2E_FRONTEND_PORT || "3000";
const baseURL = `http://localhost:${frontendPort}`;
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: { baseURL, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "phone",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: [
    {
      command: "PYTHONPATH=. .venv/bin/python tests/serve_e2e.py",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: !process.env.CI,
      cwd: "../backend",
    },
    {
      command: `npm run dev -- --port ${frontendPort}`,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
