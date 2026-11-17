import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "e2e-results.json" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    channel: "chrome",
    headless: true,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "Desktop Chrome",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: "Mobile Chrome",
      use: {
        ...devices["Pixel 7"],
      },
    },
  ],
  webServer: [
    {
      command:
        'cd .. && SIH_DATABASE_URL="postgresql://localhost:5432/sih_hospital_phase1_run_test" DATABASE_URL="postgresql://localhost:5432/sih_hospital_phase1_run_test" .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000',
      port: 8000,
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: "npm run start -- -p 3000",
      port: 3000,
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
});
