import { defineConfig } from '@playwright/test';
import base from './playwright.config';

export default defineConfig({
  ...base,
  reporter: [['list'], ['json', { outputFile: '../reports/phase2/production-playwright.json' }]],
  outputDir: '../reports/phase2/playwright-artifacts-production',
});
