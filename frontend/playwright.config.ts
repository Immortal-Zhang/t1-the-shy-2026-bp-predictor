import { defineConfig, devices } from '@playwright/test';
import { existsSync } from 'node:fs';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { outputFolder: '../reports/phase2/playwright-report', open: 'never' }], ['json', { outputFile: '../reports/phase2/playwright-results.json' }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1440, height: 1050 },
  },
  outputDir: '../reports/phase2/playwright-artifacts',
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1, ...(existsSync('/Applications/Google Chrome.app') ? { channel: 'chrome' } : {}) } },
    { name: 'webkit', use: { ...devices['Desktop Safari'], viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 } },
  ],
});
