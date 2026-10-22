import { defineConfig } from '@playwright/test';
import base from './playwright.config';

process.env.PLAYWRIGHT_REPORT_DIR = '../reports/aggressive';

export default defineConfig({
  ...base,
  timeout: 120_000,
  reporter: [['list'], ['html', { outputFolder: '../reports/aggressive/playwright-report', open: 'never' }], ['json', { outputFile: '../reports/aggressive/playwright-results.json' }]],
  outputDir: '../reports/aggressive/playwright-artifacts',
});
