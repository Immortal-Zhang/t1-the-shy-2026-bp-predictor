/** Live integration tests. Every successful prediction comes from the real API.
 * The only intercepted response is an explicitly negative 503 failure case.
 */
import { test, expect, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { AnalyzeResponse, CatalogResponse, HistoricalMatch, PlayerLookup, RosterResponse, TeamSummary } from '../src/types';

const reportDirectory = path.resolve(process.env.PLAYWRIGHT_REPORT_DIR || '../reports/phase2');
const screenshots = path.join(reportDirectory, 'screenshots');
const roleLabels = { top: '上路', jng: '打野', mid: '中路', bot: '下路', sup: '辅助' } as const;
const sideLabels = { blue: '蓝方', red: '红方' } as const;
const storageKey = 'worlds-2026-bp-predictor-v2';
let catalog: CatalogResponse;
let teams: TeamSummary[];
let latestMatch: HistoricalMatch;
let blueTeam: TeamSummary;
let redTeam: TeamSummary;
let blueRoster: RosterResponse;
let alternatePlayer: PlayerLookup;
const pageErrors = new WeakMap<Page, string[]>();

test.beforeAll(async ({ request, browser }, info) => {
  const asOf = new Date().toISOString();
  const catalogResponse = await request.get('/api/catalog', { params: { as_of: asOf } });
  expect(catalogResponse.ok()).toBeTruthy();
  catalog = await catalogResponse.json();
  const teamsResponse = await request.get('/api/teams', { params: { as_of: asOf, worlds_only: true } });
  expect(teamsResponse.ok()).toBeTruthy(); teams = (await teamsResponse.json()).teams;
  expect(teams).toHaveLength(19);
  const matches = await request.get('/api/matches', { params: { as_of: asOf, worlds_only: true } });
  expect(matches.ok()).toBeTruthy(); latestMatch = (await matches.json()).matches[0];
  expect(latestMatch?.request).toBeTruthy();
  blueTeam = teams.find(team => team.team_id === latestMatch.blue_team_id)!;
  redTeam = teams.find(team => team.team_id === latestMatch.red_team_id)!;
  expect(blueTeam).toBeTruthy(); expect(redTeam).toBeTruthy();
  const roster = await request.get(`/api/teams/${encodeURIComponent(blueTeam.team_id)}/roster`, { params: { as_of: asOf } });
  expect(roster.ok()).toBeTruthy(); blueRoster = await roster.json();
  const players = await request.get('/api/players', { params: { as_of: asOf, query: '', limit: 100 } });
  expect(players.ok()).toBeTruthy();
  const knownIds = new Set([...latestMatch.request.blue.players, ...latestMatch.request.red.players].map(player => player.player_id));
  alternatePlayer = (await players.json()).players.find((player: PlayerLookup) => !knownIds.has(player.player_id));
  expect(alternatePlayer).toBeTruthy();
  await mkdir(screenshots, { recursive: true });
  await writeFile(path.join(reportDirectory, `browser-${info.project.name}.json`), JSON.stringify({ project: info.project.name, channel: info.project.use.channel || 'Playwright WebKit', version: browser.version(), tested_at: new Date().toISOString(), real_data_game_id: latestMatch.game_id }, null, 2));
});

test.beforeEach(async ({ page }) => {
  const errors: string[] = []; pageErrors.set(page, errors);
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: /真实模型已就绪/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel('英雄搜索', { exact: true })).toBeVisible();
});

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page) || [], 'Unhandled browser application errors').toEqual([]);
});

async function loadRealReplay(page: Page) {
  await page.getByRole('button', { name: '载入一场真实 BP' }).click();
  await expect(page.getByTestId('predict-button')).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: '选择蓝方战队' })).toContainText(latestMatch.blue_team_name);
  await expect(page.getByRole('button', { name: '选择红方战队' })).toContainText(latestMatch.red_team_name);
}

async function waitForDraftImages(page: Page) {
  await expect.poll(() => page.locator('.slot-portrait img').evaluateAll(images => images.filter(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0).length), { timeout: 30_000, message: 'All ten official champion portraits must load before the screenshot' }).toBe(10);
}

async function chooseTeam(page: Page, side: 'blue' | 'red', team: TeamSummary) {
  await page.getByRole('button', { name: `选择${sideLabels[side]}战队` }).click();
  await page.getByLabel(`${sideLabels[side]}战队搜索`).fill(team.code);
  await page.getByTestId(`team-option-${side}-${team.code}`).click();
  await expect(page.getByRole('button', { name: `选择${sideLabels[side]}战队` })).toContainText(team.name, { timeout: 20_000 });
  await expect(page.getByTestId(`${side}-top-slot`).locator('.player-name')).not.toHaveText('选择选手');
}

test('real catalog, team search/autofill, manual player, Chinese/English picks, bans, swap and reset', async ({ page }, info) => {
  await chooseTeam(page, 'blue', blueTeam);
  await chooseTeam(page, 'red', redTeam);
  await expect(page.getByTestId('blue-top-slot')).toContainText(blueRoster.players.find(player => player.role === 'top')!.name);
  await expect(page.getByLabel('蓝方阵容').locator('.roster-note')).toContainText('首发请核对');
  await page.getByRole('button', { name: '修改蓝方上路选手' }).click();
  await page.getByLabel('职业选手搜索').fill(alternatePlayer.alias);
  await page.locator('.player-results button').filter({ hasText: alternatePlayer.player_id }).first().click();
  await expect(page.getByTestId('blue-top-slot')).toContainText(alternatePlayer.alias);
  await page.getByRole('button', { name: '修改蓝方上路选手' }).click();
  const original = blueRoster.players.find(player => player.role === 'top')!;
  await page.getByLabel('职业选手搜索').fill(original.name);
  await page.locator('.player-results button').filter({ hasText: original.player_id }).first().click();

  let index = 0;
  for (const side of ['blue', 'red'] as const) for (const pick of latestMatch.request[side].players) {
    const hero = catalog.champions.find(champion => champion.name_en === pick.champion || champion.id === pick.champion)!;
    expect(hero, `Real source champion ${pick.champion} must exist in verified catalog`).toBeTruthy();
    await page.getByRole('button', { name: `${sideLabels[side]}${roleLabels[pick.role]}选择英雄` }).click();
    await page.getByLabel('英雄搜索', { exact: true }).fill(index++ % 2 ? hero.name_en : hero.name_zh);
    await page.getByTestId(`champion-${hero.id}`).click();
    await expect(page.getByTestId(`${side}-${pick.role}-slot`).locator('.champion-name')).toHaveText(hero.name_zh);
  }
  await expect(page.getByTestId('predict-button')).toBeEnabled();
  const selectedHero = catalog.champions.find(champion => champion.name_en === latestMatch.request.blue.players[0]!.champion)!;
  await page.getByRole('button', { name: '红方上路选择英雄' }).click();
  await page.getByLabel('英雄搜索', { exact: true }).fill(selectedHero.name_en);
  await expect(page.getByTestId(`champion-${selectedHero.id}`)).toBeDisabled();
  const picks = new Set([...latestMatch.request.blue.players, ...latestMatch.request.red.players].map(player => player.champion));
  const ban = catalog.champions.find(champion => !picks.has(champion.name_en))!;
  await page.getByRole('button', { name: '蓝方禁用1', exact: true }).click();
  await page.getByLabel('英雄搜索', { exact: true }).fill(ban.name_zh);
  await page.getByTestId(`champion-${ban.id}`).click();
  await page.getByRole('button', { name: '红方上路选择英雄' }).click();
  await expect(page.getByTestId(`champion-${ban.id}`)).toBeDisabled();
  await page.getByLabel('BP先选权').selectOption('blue');
  await page.getByRole('button', { name: '交换蓝红方' }).click();
  await expect(page.getByRole('button', { name: '选择蓝方战队' })).toContainText(redTeam.name);
  await expect(page.getByLabel('BP先选权')).toHaveValue('red');
  await page.getByLabel('英雄搜索', { exact: true }).fill('');
  await waitForDraftImages(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(screenshots, info.project.name === 'webkit' ? 'webkit-workbench.png' : 'desktop-workbench.png') });
  await page.getByRole('button', { name: '仅重置所选英雄' }).click();
  await expect(page.locator('.player-slot .champion-name').filter({ hasText: '选择英雄' })).toHaveCount(10);
  await expect(page.getByRole('button', { name: '清除红方禁用1', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '清空 BP', exact: true }).click();
  await expect(page.locator('.ban-clear')).toHaveCount(0);
  await expect(page.getByTestId('predict-button')).toBeDisabled();
});

test('real prediction, explanation, immutable saved snapshot, page refresh, outcome and deletion', async ({ page }, info) => {
  await loadRealReplay(page);
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/analyze') && response.request().method() === 'POST');
  await page.getByTestId('predict-button').click();
  await expect(page.getByTestId('predict-button')).toBeDisabled();
  const response = await responsePromise; expect(response.status()).toBe(200);
  const actual: AnalyzeResponse = await response.json();
  expect(actual.prediction.blue_win_probability + actual.prediction.red_win_probability).toBeCloseTo(1, 12);
  const sent = response.request().postDataJSON(); expect(sent).not.toHaveProperty('blue_win'); expect(sent).not.toHaveProperty('result');
  await expect(page.getByTestId('blue-probability')).toHaveText(`${(actual.prediction.blue_win_probability * 100).toFixed(1)}%`);
  await expect(page.getByTestId('red-probability')).toHaveText(`${(actual.prediction.red_win_probability * 100).toFixed(1)}%`);
  await expect(page.getByTestId('analysis-result')).toContainText(actual.prediction.model_version);
  await expect(page.getByTestId('analysis-result')).toContainText('CatBoost SHAP');
  await page.getByTestId('analysis-result').scrollIntoViewIfNeeded();
  if (info.project.name === 'chromium') await page.screenshot({ path: path.join(screenshots, 'desktop-analysis.png') });
  await page.getByRole('tab', { name: '选手与英雄熟练度' }).click();
  await expect(page.locator('.table-panel tbody tr')).toHaveCount(10);
  await page.getByRole('tab', { name: '对线与阵容协同' }).click();
  await expect(page.locator('.matchup-list .matchup')).toHaveCount(5);
  await page.getByRole('button', { name: '保存预测', exact: true }).click();
  await page.getByRole('button', { name: /^预测历史/ }).click();
  await expect(page.getByTestId('history-record')).toHaveCount(1);
  await expect(page.getByTestId('history-record')).toContainText(actual.prediction.model_version);
  await page.getByLabel(/^实际赛果-/).selectOption('red');
  await expect(page.getByTestId('history-record')).toContainText('用户手动录入');
  await page.reload();
  await expect(page.getByRole('button', { name: /真实模型已就绪/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('blue-probability')).toHaveText(`${(actual.prediction.blue_win_probability * 100).toFixed(1)}%`);
  await expect(page.getByTestId('analysis-result')).toContainText('历史快照');
  await page.getByRole('button', { name: /^预测历史/ }).click();
  await expect(page.getByLabel(/^实际赛果-/)).toHaveValue('red');
  await page.getByRole('button', { name: '恢复阵容' }).click();
  await expect(page.getByTestId('blue-probability')).toHaveText(`${(actual.prediction.blue_win_probability * 100).toFixed(1)}%`);
  await page.getByLabel('比赛版本').fill('26.19');
  await expect(page.getByTestId('analysis-result')).toHaveCount(0);
  await page.getByRole('button', { name: '保存阵容', exact: true }).click();
  await page.getByRole('button', { name: /^预测历史/ }).click();
  await expect(page.getByTestId('history-record')).toHaveCount(2);
  await expect(page.getByTestId('history-record').filter({ hasText: '预测快照' })).toContainText(`${(actual.prediction.blue_win_probability * 100).toFixed(1)}%`);
  await page.getByRole('button', { name: /^删除记录-/ }).first().click();
  await expect(page.getByTestId('history-record')).toHaveCount(1);
  await page.getByRole('button', { name: '清空记录', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByTestId('history-record')).toHaveCount(1);
  await page.getByRole('button', { name: '清空记录', exact: true }).click();
  await page.getByRole('button', { name: '确认清空', exact: true }).click();
  await expect(page.getByTestId('history-record')).toHaveCount(0);
});

test('real wrong-version rejection and explicit unavailable-model failure with no fallback odds', async ({ page }) => {
  await loadRealReplay(page);
  await page.getByLabel('比赛版本').fill('26.19');
  const rejected = page.waitForResponse(response => response.url().endsWith('/api/analyze'));
  await page.getByTestId('predict-button').click();
  expect((await rejected).status()).toBe(422);
  await expect(page.getByRole('alert')).toContainText('26.20');
  await expect(page.getByTestId('analysis-result')).toHaveCount(0);
  await page.getByLabel('比赛版本').fill('26.20');
  // Negative fault injection only: no fabricated success response or probability.
  await page.route('**/api/analyze', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'E2E negative fault: model artifact unavailable' }) }));
  await page.getByTestId('predict-button').click();
  await expect(page.getByRole('alert')).toContainText('model artifact unavailable');
  await expect(page.getByText('真实模型当前不可用', { exact: true })).toBeVisible();
  await expect(page.getByTestId('analysis-result')).toHaveCount(0);
  await expect(page.getByTestId('predict-button')).toBeDisabled();
});

test('stale real response cannot overwrite edited inputs', async ({ page }) => {
  await loadRealReplay(page);
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let arrived: (() => void) | undefined;
  const responseArrived = new Promise<void>(resolve => { arrived = resolve; });
  await page.route('**/api/analyze', async route => {
    const response = await route.fetch(); // This is the actual backend result, not a fixture.
    expect(response.status()).toBe(200);
    arrived?.(); await gate; await route.fulfill({ response });
  });
  await page.getByTestId('predict-button').click();
  await responseArrived;
  await page.getByLabel('BP先选权').selectOption('unknown');
  release?.();
  await expect(page.getByText('输入已改变，已丢弃过期响应，请重新预测。')).toBeVisible();
  await expect(page.getByTestId('analysis-result')).toHaveCount(0);
});

test('responsive desktop/mobile layout and real-match browsing remain usable', async ({ page }, info) => {
  await loadRealReplay(page);
  await waitForDraftImages(page);
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(await overflow()).toBeLessThanOrEqual(1);
  if (info.project.name === 'chromium') await page.screenshot({ path: path.join(screenshots, 'mobile-workbench.png') });
  await page.getByRole('button', { name: /^真实比赛/ }).click();
  await expect(page.locator('.match-card').first()).toBeVisible();
  // Loading a replay changes as_of; the currently replayed game is correctly
  // absent from the earlier-known-results list. Browse an eligible earlier game.
  const eligibleId = (await page.locator('.match-card .match-id').first().textContent())!;
  await page.getByLabel('历史比赛搜索').fill(eligibleId);
  await expect(page.locator('.match-card')).toHaveCount(1);
  await expect(page.locator('.match-card')).toContainText('来源赛果：');
  await page.getByRole('button', { name: '载入赛前 BP' }).click();
  await expect(page.getByTestId('predict-button')).toBeEnabled({ timeout: 30_000 });
  expect(await overflow()).toBeLessThanOrEqual(1);
  const state = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}').state, storageKey);
  expect(state.game_id).toBe(eligibleId);
  expect(state.blue.players).toHaveLength(5);
  expect(state.red.players).toHaveLength(5);
});

test('verified Fearless context records ten real catalog heroes and prevents repeat picks', async ({ page }) => {
  test.skip(!catalog.worlds.rules.verified, 'Official applicable Fearless rules are unavailable; must not fabricate a rule');
  await loadRealReplay(page);
  await page.getByLabel('系列赛格式').selectOption('bo3');
  await page.getByLabel(/^启用.*已核验规则$/).check();
  await page.getByRole('button', { name: '记录前序小局英雄' }).click();
  const dialog = page.getByRole('dialog', { name: /记录 GAME 1/ });
  // Structural context exercise using the real game's ten catalog entries.
  // This is never submitted as an assertion that those heroes were an earlier map.
  for (const pick of [...latestMatch.request.blue.players, ...latestMatch.request.red.players]) {
    const hero = catalog.champions.find(champion => champion.name_en === pick.champion)!;
    await page.getByLabel('前序英雄搜索', { exact: true }).fill(hero.name_en);
    await dialog.locator('.prior-champion-grid button').filter({ hasText: hero.name_zh }).click();
  }
  await page.getByRole('button', { name: '保存该局的 10 个英雄' }).click();
  await expect(page.locator('.prior-game')).toHaveCount(1);
  await expect(page.getByTestId('predict-button')).toBeDisabled();
  const blocked = catalog.champions.find(champion => champion.name_en === latestMatch.request.blue.players[0]!.champion)!;
  await page.getByLabel('英雄搜索', { exact: true }).fill(blocked.name_en);
  await expect(page.getByTestId(`champion-${blocked.id}`)).toBeDisabled();
  await page.getByRole('button', { name: '删除前序小局1' }).click();
  await expect(page.getByTestId('predict-button')).toBeEnabled();
});
