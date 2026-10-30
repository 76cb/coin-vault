import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? 8765);
const executablePath = process.env.PW_CHROME_PATH; // optional: use an installed Chrome instead of a downloaded one

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npm run build && ./scripts/e2e-server.sh",
    url: `http://127.0.0.1:${port}/api/v1/health`,
    timeout: 120_000,
    reuseExistingServer: false,
  },
});
