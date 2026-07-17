import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:5173/app/", trace: "on-first-retry" },
  webServer: {
    command: "VITE_USE_MOCKS=true npm run dev -- --host 0.0.0.0",
    url: "http://127.0.0.1:5173/app/",
    reuseExistingServer: true,
  },
  projects: [
    {
      name: "telephone",
      use: { ...devices["Pixel 5"], viewport: { width: 360, height: 800 } },
    },
    {
      name: "ordinateur",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
});
