import { describe, expect, it } from 'vitest';
import { blockedChampions, buildRequest, championAvailability, initialDraft, parseApiDate, searchChampions, sortedHistory, validateDraft } from './domain';
import { championFixtures, completeFixture, TEST_TIME } from './test/fixtures';

describe('draft validation (synthetic structural fixtures)', () => {
  it('requires real inputs before complete BP prediction', () => {
    expect(validateDraft(initialDraft(TEST_TIME))).toContain('请先选择蓝红双方战队');
    expect(validateDraft(completeFixture())).toEqual([]);
  });
  it('detects same teams, players and champions', () => {
    const state = completeFixture();
    state.red.team_id = state.blue.team_id;
    state.red.players[0] = { ...state.red.players[0]!, player_id: state.blue.players[0]!.player_id, champion: state.blue.players[0]!.champion };
    expect(validateDraft(state)).toEqual(expect.arrayContaining(['蓝红双方不能是同一支战队', '同一名选手不能占据多个位置', '同一局不能重复选择英雄']));
  });
  it('rejects bans overlapping picks and duplicate bans', () => {
    const state = completeFixture();
    state.blue.bans[0] = state.red.players[0]!.champion;
    state.red.bans[2] = state.blue.bans[0]!;
    expect(validateDraft(state)).toEqual(expect.arrayContaining(['不能重复禁用同一英雄', '已禁用的英雄不能被选择']));
  });
  it('detects missing positions and future cutoff', () => {
    const state = completeFixture();
    state.blue.players = state.blue.players.slice(0, 4);
    state.settings.as_of = '2026-10-23T00:00:00Z';
    expect(validateDraft(state)).toEqual(expect.arrayContaining(['蓝方必须拥有五个不同位置', '数据截止时间不能晚于比赛开始时间']));
  });
  it('rejects a future observed autofill but permits exact historical-game timestamp equality', () => {
    const state = completeFixture();
    state.blue.roster_observed_at = '2026-10-23T00:00:00Z';
    expect(validateDraft(state)).toContain('蓝方阵容观测晚于信息截止时间，请重新选择战队并核对选手');
    state.blue.roster_observed_at = TEST_TIME;
    expect(validateDraft(state)).toEqual([]);
  });
  it('allows editing the current slot without blocking its own champion', () => {
    const state = completeFixture();
    const champion = state.blue.players[0]!.champion;
    expect(championAvailability(champion, state)).toBe('已被选择');
    expect(championAvailability(champion, state, { side: 'blue', role: 'top' })).toBeNull();
  });
  it('blocks a ban in every pick slot while allowing its own ban slot', () => {
    const state = completeFixture(); state.red.bans[1] = 'UnitBan';
    expect(championAvailability('UnitBan', state, { side: 'blue', role: 'top' })).toBe('已被禁用');
    expect(championAvailability('UnitBan', state, { side: 'red', banIndex: 1 })).toBeNull();
  });
  it('treats Fearless as explicit context requiring verified rules and full earlier maps', () => {
    const state = completeFixture();
    state.series = { enabled: true, format: 'bo3', previous_games: [{ blue_champions: [state.blue.players[0]!.champion], red_champions: [] }] };
    expect(blockedChampions(state.series)).toEqual([state.blue.players[0]!.champion]);
    expect(championAvailability(state.blue.players[0]!.champion, state)).toContain('Fearless');
    expect(validateDraft(state, false)).toEqual(expect.arrayContaining(['官方 Fearless 规则尚未核验，暂不能启用', '每个前序小局须记录双方完整十个英雄', '当前阵容包含 Fearless 已使用英雄']));
    state.series.enabled = false;
    expect(blockedChampions(state.series)).toEqual([]);
  });
  it('exports only the pregame request contract', () => {
    const state = completeFixture(); state.game_id = 'unit-game';
    const request = buildRequest(state);
    expect(request.game_id).toBe('unit-game');
    expect(request.blue.players).toHaveLength(5);
    expect(request.blue.players[0]).toEqual({ role: 'top', player_id: 'unit-player-blue-top', champion: 'Unitbluetop' });
    expect(request).not.toHaveProperty('result');
    expect(request.blue.players[0]).not.toHaveProperty('name');
    expect(request).not.toHaveProperty('series_context');
  });
  it('searches Chinese, English, title and role from actual catalog fields', () => {
    expect(searchChampions(championFixtures, '测试甲').map(value => value.id)).toEqual(['UnitAlpha']);
    expect(searchChampions(championFixtures, 'unit beta', 'sup').map(value => value.id)).toEqual(['UnitBeta']);
    expect(searchChampions(championFixtures, '守护者').map(value => value.id)).toEqual(['UnitBeta']);
    expect(searchChampions(championFixtures, 'Unit Alpha', 'top')).toEqual([]);
  });
  it('sorts history by match date without mutating original order', () => {
    const values = [{ match_date: '2026-01-01', created_at: '2026-10-22' }, { match_date: '2026-10-01', created_at: '2026-10-20' }];
    expect(sortedHistory(values)[0]!.match_date).toBe('2026-10-01');
    expect(values[0]!.match_date).toBe('2026-01-01');
  });
  it('normalizes source timestamp separators for Safari Date parsing', () => {
    expect(parseApiDate('2025-12-30 00:00:00+00:00').toISOString()).toBe('2025-12-30T00:00:00.000Z');
  });
});
