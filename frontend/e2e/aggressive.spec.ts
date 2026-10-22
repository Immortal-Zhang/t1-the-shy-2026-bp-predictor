/** Real-model browser tests. Success values are read from actual /analyze calls. */
import { test, expect, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { AnalyzeResponse, AvailableJudgment } from '../src/types';

const reportDirectory = path.resolve('../reports/aggressive');
const number = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 1 });
const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const errors = new WeakMap<Page, string[]>();

test.beforeEach(async ({ page }) => {
  const failures: string[] = []; errors.set(page, failures);
  page.on('pageerror', error => failures.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: /真实模型已就绪/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: '载入一场真实 BP' }).click();
  await expect(page.getByTestId('predict-button')).toBeEnabled({ timeout: 30_000 });
});

test.afterEach(async ({ page }) => {
  expect(errors.get(page) || []).toEqual([]);
});

async function predict(page: Page): Promise<{ actual: AnalyzeResponse; judgment: AvailableJudgment }> {
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/analyze') && response.request().method() === 'POST', { timeout: 90_000 });
  await page.getByTestId('predict-button').click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const actual: AnalyzeResponse = await response.json();
  expect(actual.judgment?.available).toBe(true);
  if (!actual.judgment?.available) throw new Error('Real judgment artifact was unavailable; cannot claim this test passed.');
  await expect(page.getByTestId('judgment-panel')).toBeVisible();
  return { actual, judgment: actual.judgment };
}

test('aggressive default, same evidence in extreme, standard calibration and immutable history', async ({ page }, info) => {
  let postCount = 0;
  page.on('request', request => { if (request.url().endsWith('/api/analyze') && request.method() === 'POST') postCount++; });
  await expect(page.getByTestId('mode-aggressive')).toHaveAttribute('aria-pressed', 'true');
  const { actual, judgment } = await predict(page);
  expect(judgment.support.blue + judgment.support.red).toBeCloseTo(100, 8);
  expect(actual.prediction.blue_win_probability + actual.prediction.red_win_probability).toBeCloseTo(1, 12);
  await expect(page.getByTestId('blue-support')).toHaveText(`${number(judgment.support.blue)}/ 100`);
  await expect(page.getByTestId('red-support')).toHaveText(`${number(judgment.support.red)}/ 100`);
  await expect(page.getByTestId('advantage-grade')).toHaveText(judgment.advantage.label);
  await expect(page.getByTestId('predicted-winner')).toContainText(judgment.winner.side === 'blue' ? '蓝方' : '红方');
  await expect(page.getByTestId('judgment-panel')).toContainText('非获胜概率');
  await expect(page.getByTestId('judgment-panel')).toContainText('实验性判断');
  await expect(page.getByTestId('judgment-experiment-note')).toHaveText(judgment.evaluation.comparison_note);
  await expect(page.getByTestId('judgment-reason')).toHaveCount(3);
  await expect(page.getByTestId('judgment-risk')).toHaveCount(2);
  await expect(page.getByTestId('draft-weakness')).toContainText(judgment.bp_assessment.weakness.title);
  await expect(page.getByTestId('judgment-driver')).toHaveText(judgment.driver.label);
  await expect(page.getByTestId('blue-probability')).not.toBeVisible();
  await mkdir(path.join(reportDirectory, 'screenshots'), { recursive: true });
  await page.getByTestId('judgment-panel').screenshot({ path: path.join(reportDirectory, 'screenshots', `${info.project.name}-aggressive.png`) });
  const winnerText = await page.getByTestId('predicted-winner').textContent();
  await page.getByTestId('mode-extreme').click();
  await expect(page.getByTestId('predicted-winner')).toHaveText(winnerText!);
  await expect(page.getByTestId('red-support')).toHaveText(`${number(judgment.support.red)}/ 100`);
  await expect(page.getByTestId('advantage-grade')).toHaveText(judgment.advantage.label);
  await expect(page.getByText('判断失效的两个条件')).toBeVisible();
  await expect(page.locator('.judgment-evidence-grid > section').first()).toHaveClass('judgment-risks');
  if (info.project.name === 'chromium') await page.getByTestId('judgment-panel').screenshot({ path: path.join(reportDirectory, 'screenshots', 'desktop-extreme.png') });
  await page.getByText('技术详情：原始校准概率、支持指数定义与回测', { exact: true }).click();
  await expect(page.getByTestId('blue-probability')).toBeVisible();
  await expect(page.getByTestId('blue-probability')).toHaveText(percent(actual.prediction.blue_win_probability));
  await expect(page.getByTestId('judgment-technical')).toContainText(judgment.evaluation.scope);
  await expect(page.getByTestId('judgment-technical').locator('.judgment-evaluation-table tbody tr')).toHaveCount(judgment.evaluation.grades.length);
  await page.getByTestId('mode-standard').click();
  await expect(page.getByTestId('judgment-panel')).toHaveCount(0);
  await expect(page.getByTestId('blue-probability')).toBeVisible();
  await expect(page.getByTestId('blue-probability')).toHaveText(percent(actual.prediction.blue_win_probability));
  await expect(page.getByTestId('red-probability')).toHaveText(percent(actual.prediction.red_win_probability));
  if (info.project.name === 'chromium') await page.locator('.result-hero').screenshot({ path: path.join(reportDirectory, 'screenshots', 'desktop-standard.png') });
  await page.getByTestId('mode-aggressive').click();
  expect(postCount, 'Mode changes must not refetch or fabricate predictions').toBe(1);
  await page.getByRole('button', { name: '保存预测', exact: true }).click();
  await page.getByRole('button', { name: /^预测历史/ }).click();
  await expect(page.getByTestId('history-record')).toHaveCount(1);
  await expect(page.getByTestId('history-record')).toContainText('支持指数');
  await page.getByLabel(/^实际赛果-/).selectOption(judgment.winner.side);
  await expect(page.getByTestId('history-record')).toContainText('激进判断命中');
  await page.reload();
  await expect(page.getByTestId('predicted-winner')).toHaveText(winnerText!);
  await expect(page.getByTestId('mode-aggressive')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('red-support')).toHaveText(`${number(judgment.support.red)}/ 100`);
  await expect(page.getByTestId('analysis-result')).toContainText('历史快照');
  await page.getByRole('button', { name: /^预测历史/ }).click();
  await page.getByRole('button', { name: '恢复阵容' }).click();
  await expect(page.getByTestId('predicted-winner')).toHaveText(winnerText!);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await writeFile(path.join(reportDirectory, `aggressive-browser-${info.project.name}.json`), JSON.stringify({
    tested_at: new Date().toISOString(), browser: info.project.name, real_api_status: 200,
    judgment_model: judgment.model_version, original_model: actual.prediction.model_version,
    winner: judgment.winner, support: judgment.support, original_blue_probability: actual.prediction.blue_win_probability,
    unchanged_across_modes: true, original_history_restored: true, page_errors: errors.get(page), horizontal_overflow_px: overflow,
  }, null, 2));
});

test('real aggressive judgment remains readable on mobile in all modes', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { actual, judgment } = await predict(page);
  await expect(page.getByTestId('predicted-winner')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  await expect(page.getByTestId('blue-support')).toHaveText(`${number(judgment.support.blue)}/ 100`);
  if (info.project.name === 'chromium') {
    await mkdir(path.join(reportDirectory, 'screenshots'), { recursive: true });
    await page.getByTestId('judgment-panel').screenshot({ path: path.join(reportDirectory, 'screenshots', 'mobile-aggressive.png') });
  }
  await page.getByTestId('mode-extreme').click();
  await expect(page.getByTestId('judgment-risk')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  await page.getByTestId('mode-standard').click();
  await expect(page.getByTestId('blue-probability')).toHaveText(percent(actual.prediction.blue_win_probability));
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
});
