import { defineConfig, devices } from "@playwright/test"

const webBaseURL = process.env.E2E_WEB_URL || "http://127.0.0.1:3100"
const apiBaseURL = process.env.E2E_API_URL || "http://127.0.0.1:4100"

export default defineConfig({
  testDir: "./tests/e2e/specs",
  outputDir: "./test-results",
  globalSetup: "./tests/e2e/global-setup.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [
        ["line"],
        ["html", { outputFolder: "playwright-report", open: "never" }],
        ["junit", { outputFile: "test-results/junit.xml" }],
      ]
    : [
        ["list"],
        ["html", { outputFolder: "playwright-report", open: "never" }],
      ],
  use: {
    baseURL: webBaseURL,
    headless: process.env.E2E_HEADED !== "1",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: "bash tests/e2e/scripts/start-api.sh",
      url: `${apiBaseURL}/health/ready`,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "ignore",
    },
    {
      command: "bash tests/e2e/scripts/start-web.sh",
      url: webBaseURL,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
  projects: [
    {
      name: "auth-setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "chromium-owner",
      dependencies: ["auth-setup"],
      testIgnore: [/auth\.setup\.ts/, /permissions\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        storageState: "tests/e2e/.auth/owner.json",
      },
    },
    {
      name: "chromium-viewer",
      dependencies: ["auth-setup"],
      testMatch: /permissions\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: "tests/e2e/.auth/viewer.json",
      },
    },
  ],
})
