import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.CSRS_MANUAL_BASE_URL ?? "http://127.0.0.1:5173";

export default defineConfig({
  testDir: "./manual-e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  outputDir: "../tmp/manual-playwright",
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    viewport: { width: 1440, height: 1000 },
    locale: "fr-FR",
    timezoneId: "Africa/Abidjan",
    colorScheme: "light",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.CSRS_MANUAL_CHROMIUM ?? "/usr/bin/chromium",
      args: ["--no-sandbox"],
    },
  },
});
