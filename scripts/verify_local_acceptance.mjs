/** Final live acceptance. Structural series fixtures are never performance data. */
import { chromium, webkit } from '../frontend/node_modules/playwright/index.mjs';
import { expect } from '../frontend/node_modules/@playwright/test/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const root = fileURLToPath(new URL('..', import.meta.url));
const reports = path.join(root, 'reports/acceptance');
await mkdir(reports, { recursive: true });
const outcomes = [];
for (const [name, engine, options] of [['chrome', chromium, { channel: 'chrome' }], ['webkit', webkit, {}]]) {
  const browser = await engine.launch({ headless: true, ...options });
  const context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1050 } });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto('/');
    await expect(page.getByRole('button', { name: /真实模型已就绪/ })).toBeVisible();
    await page.getByRole('button', { name: '载入一场真实 BP' }).click();
    await expect(page.getByTestId('predict-button')).toBeEnabled();
    const catalog = await (await page.request.get('/api/catalog', { params: { as_of: new Date().toISOString() } })).json();
    const state = await page.evaluate(() => JSON.parse(localStorage.getItem('worlds-2026-bp-predictor-v2')).state);
    const realPicks = [...state.blue.players, ...state.red.players].map(p => p.champion);
    expect(new Set(realPicks).size).toBe(10);
    expect(new Set([...state.blue.players, ...state.red.players].map(p => p.player_id)).size).toBe(10);

    async function predict() {
      const started = Date.now();
      const responsePromise = page.waitForResponse(r => r.url().endsWith('/api/analyze') && r.request().method() === 'POST', { timeout: 90_000 });
      await page.getByTestId('predict-button').click();
      const response = await responsePromise;
      expect(response.status()).toBe(200);
      const sent = response.request().postDataJSON();
      expect(sent.blue.players).toHaveLength(5); expect(sent.red.players).toHaveLength(5);
      expect(sent).not.toHaveProperty('blue_win');
      const actual = await response.json();
      expect(actual.judgment.available).toBe(true);
      expect(actual.prediction.blue_win_probability + actual.prediction.red_win_probability).toBeCloseTo(1, 12);
      await expect(page.getByTestId('predicted-winner')).toBeVisible();
      return { request: sent, response: actual, elapsed_seconds: (Date.now() - started) / 1000 };
    }
    const first = await predict();
    console.log(`${name}: real ten-player prediction HTTP200`);
    await page.getByTestId('mode-extreme').click();
    await expect(page.getByTestId('judgment-risk')).toHaveCount(2);
    await page.getByTestId('mode-standard').click();
    await expect(page.getByTestId('blue-probability')).toHaveText(`${(first.response.prediction.blue_win_probability * 100).toFixed(1)}%`);
    await page.getByTestId('mode-aggressive').click();

    await page.getByLabel('系列赛格式').selectOption('bo5');
    await expect(page.getByTestId('analysis-result')).toHaveCount(0);
    await page.getByLabel(/^启用.*已核验规则$/).check();
    // Four disjoint sets from the real catalog test UI constraints only.
    // They do not assert any historical series took place and are all removed
    // before the second real prediction request.
    const samplePicks = [...realPicks, ...catalog.champions.map(c => c.name_en).filter(c => !realPicks.includes(c))].slice(0, 40);
    for (let index = 0; index < 4; index++) {
      await page.getByRole('button', { name: '记录前序小局英雄' }).click();
      const dialog = page.getByRole('dialog', { name: new RegExp(`记录 GAME ${index + 1}`) });
      for (const champion of samplePicks.slice(index * 10, index * 10 + 10)) {
        const hero = catalog.champions.find(c => c.name_en === champion);
        await page.getByLabel('前序英雄搜索', { exact: true }).fill(hero.name_en);
        await dialog.locator('.prior-champion-grid button').filter({ hasText: hero.name_zh }).click();
      }
      await page.getByRole('button', { name: '保存该局的 10 个英雄' }).click();
    }
    await expect(page.locator('.prior-game')).toHaveCount(4);
    await expect(page.getByRole('button', { name: '记录前序小局英雄' })).toBeDisabled();
    await expect(page.getByTestId('predict-button')).toBeDisabled();
    const blocked = catalog.champions.find(c => c.name_en === realPicks[0]);
    await page.getByLabel('英雄搜索', { exact: true }).fill(blocked.name_en);
    await expect(page.getByTestId(`champion-${blocked.id}`)).toBeDisabled();
    for (let index = 4; index >= 1; index--) await page.getByRole('button', { name: `删除前序小局${index}`, exact: true }).click();
    await expect(page.getByTestId('predict-button')).toBeEnabled();
    const bo5 = await predict();
    expect(bo5.request.draft_context).toMatchObject({ enabled: true, format: 'bo5', previous_games: [] });
    expect(bo5.response.draft_context_validation.enabled).toBe(true);
    expect(bo5.response.prediction.blue_win_probability).toBe(first.response.prediction.blue_win_probability);
    expect(bo5.response.judgment.support).toEqual(first.response.judgment.support);
    console.log(`${name}: Bo5 four-map exclusions, removal and current-map prediction passed`);

    // Actual BP mutation must invalidate old outputs; incomplete draft cannot
    // quietly reuse the old prediction or produce partial-draft fake odds.
    await page.getByRole('button', { name: '交换蓝红方' }).click();
    await expect(page.getByTestId('analysis-result')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '选择蓝方战队' })).toContainText(state.red.team_name);
    await page.getByRole('button', { name: '仅重置所选英雄' }).click();
    await expect(page.getByTestId('predict-button')).toBeDisabled();
    await expect(page.locator('.player-slot .champion-name').filter({ hasText: '选择英雄' })).toHaveCount(10);
    expect(errors).toEqual([]);
    const health = await (await page.request.get('/api/health')).json();
    expect(health.series_prediction_supported).toBe(false);
    const result = {
      checked_at: new Date().toISOString(), browser: name, browser_version: browser.version(), platform: os.platform(),
      true_game_id: first.request.game_id, request: first.request,
      prediction: first.response.prediction, judgment: first.response.judgment,
      checks: { ten_real_players_and_champions: true, real_http_prediction: true, three_display_modes: true,
        bo5_four_previous_maps: true, fearless_exclusion: true, previous_maps_removed_before_prediction: true,
        bo5_current_map_http_prediction: true, context_does_not_fake_series_probability: true,
        editing_invalidates_result: true, incomplete_bp_prediction_blocked: true },
      timings: { first_prediction_seconds: first.elapsed_seconds, bo5_current_map_seconds: bo5.elapsed_seconds },
      page_errors: errors,
      scope: 'Bo5 context test uses explicitly structural catalog fixtures only; real inference uses observed match BP with zero previous maps. No invented historical series or results.',
      unsupported: ['partial-draft sequential live probabilities', 'Bo5 whole-series win probability'],
    };
    await writeFile(path.join(reports, `${name}.json`), JSON.stringify(result, null, 2));
    outcomes.push({ browser: name, passed: true, timings: result.timings, page_errors: errors });
  } catch (error) {
    await writeFile(path.join(reports, `${name}-failure.json`), JSON.stringify({ error: String(error), page_errors: errors }, null, 2));
    throw error;
  } finally { await context.close(); await browser.close(); }
}
await writeFile(path.join(reports, 'summary.json'), JSON.stringify({ checked_at: new Date().toISOString(), outcomes }, null, 2));
console.log(JSON.stringify(outcomes));
