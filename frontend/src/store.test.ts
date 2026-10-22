import { beforeEach, describe, expect, it } from 'vitest';
import { buildRequest, initialDraft, ROLES } from './domain';
import { STORAGE_KEY, usePredictorStore } from './store';
import { analysisFixture, completeFixture, judgmentFixture, rosterFixture, teamFixture, TEST_TIME } from './test/fixtures';

beforeEach(() => {
  localStorage.clear();
  usePredictorStore.setState({ ...initialDraft(TEST_TIME), displayMode: 'aggressive', result: null, resultSource: null, history: [], inputRevision: 0, storageWarning: null });
});

describe('persistent draft state with synthetic structural fixtures only', () => {
  it('defaults to aggressive and treats mode switching as presentation only', () => {
    expect(usePredictorStore.getState().displayMode).toBe('aggressive');
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setResult(analysisFixture());
    const previous = usePredictorStore.getState();
    const request = buildRequest(previous);
    previous.setDisplayMode('extreme');
    const current = usePredictorStore.getState();
    expect(current.inputRevision).toBe(previous.inputRevision);
    expect(current.result).toBe(previous.result);
    expect(buildRequest(current)).toEqual(request);
    expect(current.displayMode).toBe('extreme');
  });
  it('retains mode preference across reloads and defaults older storage to aggressive', async () => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setDisplayMode('standard');
    const serialized = localStorage.getItem(STORAGE_KEY)!;
    usePredictorStore.getState().setDisplayMode('extreme');
    localStorage.setItem(STORAGE_KEY, serialized);
    await usePredictorStore.persist.rehydrate();
    expect(usePredictorStore.getState().displayMode).toBe('standard');
    const older = JSON.parse(serialized); delete older.state.displayMode;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(older));
    await usePredictorStore.persist.rehydrate();
    expect(usePredictorStore.getState().displayMode).toBe('aggressive');
    expect(usePredictorStore.getState().blue.team_id).toBe('unit-team-blue');
  });
  it('saves the original judgment evidence and support index without reinterpreting old records', async () => {
    usePredictorStore.setState(completeFixture());
    const result = analysisFixture(); result.judgment = judgmentFixture();
    usePredictorStore.getState().setResult(result);
    const id = usePredictorStore.getState().saveRecord()!;
    result.judgment.support.red = 99;
    result.judgment.reasons[0]!.title = 'Changed outside store';
    usePredictorStore.getState().setDisplayMode('extreme');
    usePredictorStore.getState().resetChampions();
    usePredictorStore.getState().loadRecord(id);
    const restored = usePredictorStore.getState().result!.judgment!;
    expect(restored.available).toBe(true);
    if (restored.available) {
      expect(restored.support.red).toBe(78);
      expect(restored.reasons[0]!.title).toBe('单元依据甲');
      expect(restored.model_version).toBe('SYNTHETIC_JUDGMENT_ONLY');
    }
    expect(usePredictorStore.getState().displayMode).toBe('extreme');
    expect(usePredictorStore.getState().resultSource).toBe('saved');
  });
  it('rejects malformed judgment instead of rendering an invented confidence', () => {
    const result = analysisFixture(); result.judgment = judgmentFixture();
    result.judgment.support.red = 140;
    expect(() => usePredictorStore.getState().setResult(result)).toThrow('无效概率');
    expect(usePredictorStore.getState().result).toBeNull();
  });
  it.each(['settings', 'team', 'player', 'champion', 'ban', 'series', 'swap', 'clear', 'heroes', 'reset'] as const)('invalidates old probabilities when %s input changes', mutation => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setResult(analysisFixture());
    const before = usePredictorStore.getState().inputRevision;
    const state = usePredictorStore.getState();
    switch (mutation) {
      case 'settings': state.setSettings({ as_of: '2026-10-21T00:00:00Z' }); break;
      case 'team': state.setTeam('blue', teamFixture, rosterFixture); break;
      case 'player': state.setPlayer('blue', 'top', { player_id: 'unit-new', name: 'Unit new' }); break;
      case 'champion': state.setChampion('blue', 'top', 'NewUnitPick'); break;
      case 'ban': state.setBan('blue', 0, 'NewUnitBan'); break;
      case 'series': state.setSeries({ format: 'bo3' }); break;
      case 'swap': state.swapSides(); break;
      case 'clear': state.clearBP(); break;
      case 'heroes': state.resetChampions(); break;
      case 'reset': state.resetAll(); break;
    }
    expect(usePredictorStore.getState().result).toBeNull();
    expect(usePredictorStore.getState().inputRevision).toBeGreaterThan(before);
  });
  it('begins with no fabricated prediction', () => {
    expect(usePredictorStore.getState().result).toBeNull();
    expect(usePredictorStore.getState().saveRecord()).toBeNull();
  });
  it('fills one known player in every role with observed roster provenance', () => {
    usePredictorStore.getState().setTeam('blue', teamFixture, rosterFixture);
    const team = usePredictorStore.getState().blue;
    expect(team.players.map(value => value.role)).toEqual(ROLES);
    expect(team.players.every(value => value.player_id.startsWith('unit-player-'))).toBe(true);
    expect(team.roster_notice).toBe(rosterFixture.notice);
  });
  it('manual player replacement does not attribute old-player statistics to the replacement', () => {
    usePredictorStore.getState().setTeam('blue', teamFixture, rosterFixture);
    usePredictorStore.getState().setChampion('blue', 'top', 'UnitPick');
    usePredictorStore.getState().setPlayer('blue', 'top', { player_id: 'new-unit-id', name: 'New unit fixture' });
    const pick = usePredictorStore.getState().blue.players[0]!;
    expect(pick.player_id).toBe('new-unit-id');
    expect(pick.champion).toBe('UnitPick');
    expect(pick.history_games).toBeUndefined();
  });
  it('changing the information cutoff clears roster IDs and historical statistics while preserving draft choices', () => {
    usePredictorStore.getState().setTeam('blue', teamFixture, rosterFixture);
    usePredictorStore.getState().setChampion('blue', 'top', 'UnitPick');
    usePredictorStore.getState().setBan('blue', 0, 'UnitBan');
    usePredictorStore.getState().setResult(analysisFixture());
    usePredictorStore.getState().setSettings({ as_of: '2026-10-01T00:00:00Z' });
    const state = usePredictorStore.getState();
    expect(state.blue.team_id).toBe(teamFixture.team_id);
    expect(state.blue.players[0]!.champion).toBe('UnitPick');
    expect(state.blue.bans[0]).toBe('UnitBan');
    expect(state.blue.players.every(player => player.player_id === '' && player.name === '' && player.history_games === undefined)).toBe(true);
    expect(state.blue.roster_observed_at).toBeNull();
    expect(state.blue.roster_notice).toContain('信息截止时间已改变');
    expect(state.result).toBeNull();
  });
  it('does not erase roster evidence for a textually different representation of the same cutoff instant', () => {
    usePredictorStore.getState().setTeam('blue', teamFixture, rosterFixture);
    usePredictorStore.getState().setSettings({ as_of: '2026-10-22T08:00:00+08:00' });
    expect(usePredictorStore.getState().blue.players[0]!.player_id).toBe('unit-player-top');
    expect(usePredictorStore.getState().blue.players[0]!.history_games).toBe(7);
  });
  it('prevents duplicate picks, picked bans, banned picks, and bad ban indices', () => {
    const store = usePredictorStore.getState();
    expect(store.setChampion('blue', 'top', 'UnitPick')).toBe(true);
    expect(store.setChampion('red', 'mid', 'UnitPick')).toBe(false);
    expect(store.setBan('red', 0, 'UnitPick')).toBe(false);
    expect(store.setBan('red', 0, 'UnitBan')).toBe(true);
    expect(store.setChampion('red', 'mid', 'UnitBan')).toBe(false);
    expect(store.setBan('blue', 5, 'UnitOther')).toBe(false);
  });
  it('accepts ten distinct picks and invalidates a previous result on edits', () => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setResult(analysisFixture());
    expect(usePredictorStore.getState().result).not.toBeNull();
    usePredictorStore.getState().setChampion('blue', 'top', 'NewUnitPick');
    expect(usePredictorStore.getState().result).toBeNull();
    expect(usePredictorStore.getState().inputRevision).toBe(1);
  });
  it('rejects stale asynchronous results and impossible probabilities', () => {
    const revision = usePredictorStore.getState().inputRevision;
    usePredictorStore.getState().setSettings({ patch: '26.19' });
    expect(usePredictorStore.getState().setResult(analysisFixture(), revision)).toBe(false);
    const invalid = analysisFixture(); invalid.prediction.blue_win_probability = 1.1;
    expect(() => usePredictorStore.getState().setResult(invalid)).toThrow('无效概率');
    expect(usePredictorStore.getState().result).toBeNull();
  });
  it('swaps the full draft and carries pick entitlement with the corresponding team', () => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setSettings({ first_pick_side: 'blue' });
    usePredictorStore.getState().setBan('blue', 0, 'UnitBan');
    const before = structuredClone(usePredictorStore.getState().blue);
    usePredictorStore.getState().swapSides();
    expect(usePredictorStore.getState().red).toEqual(before);
    expect(usePredictorStore.getState().settings.first_pick_side).toBe('red');
  });
  it('hero-only reset retains bans while clear BP removes both picks and bans', () => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setBan('blue', 0, 'UnitBan');
    usePredictorStore.getState().resetChampions();
    expect(usePredictorStore.getState().blue.bans[0]).toBe('UnitBan');
    expect(usePredictorStore.getState().blue.players.every(value => !value.champion)).toBe(true);
    usePredictorStore.getState().clearBP();
    expect(usePredictorStore.getState().blue.bans.every(value => value === null)).toBe(true);
    expect(usePredictorStore.getState().blue.team_id).toBe('unit-team-blue');
  });
  it('saves an incomplete draft without a request or predicted probability', () => {
    const id = usePredictorStore.getState().saveDraft('Unit draft');
    const record = usePredictorStore.getState().history.find(value => value.id === id)!;
    expect(record.recordType).toBe('draft'); expect(record.result).toBeNull(); expect(record.request).toBeNull();
  });
  it('preserves original prediction/model metadata when models or input later change', () => {
    usePredictorStore.setState(completeFixture());
    const original = analysisFixture();
    usePredictorStore.getState().setResult(original);
    const id = usePredictorStore.getState().saveRecord()!;
    original.prediction.blue_win_probability = 0.9;
    usePredictorStore.getState().setSettings({ patch: '26.19' });
    const newer = analysisFixture(); newer.prediction.model_version = 'NEW_UNIT_MODEL';
    usePredictorStore.getState().setResult(newer);
    const saved = usePredictorStore.getState().history[0]!;
    expect(saved.result!.prediction.model_version).toBe('SYNTHETIC_UNIT_TEST_ONLY');
    expect(saved.result!.prediction.blue_win_probability).toBe(0.63);
    usePredictorStore.getState().loadRecord(id);
    expect(usePredictorStore.getState().resultSource).toBe('saved');
    expect(usePredictorStore.getState().settings.patch).toBe('26.20');
  });
  it('records an actual outcome separately without rewriting predicted odds', () => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setResult(analysisFixture());
    const id = usePredictorStore.getState().saveRecord()!;
    usePredictorStore.getState().setActualResult(id, 'red', 'manual');
    const record = usePredictorStore.getState().history[0]!;
    expect(record.actual_result).toBe('red'); expect(record.actual_result_source).toBe('manual');
    expect(record.result!.prediction.blue_win_probability).toBe(0.63);
  });
  it('deletes selected records and clears history without resetting the active draft', () => {
    usePredictorStore.setState(completeFixture());
    const first = usePredictorStore.getState().saveDraft(); usePredictorStore.getState().saveDraft();
    usePredictorStore.getState().deleteRecord(first);
    expect(usePredictorStore.getState().history).toHaveLength(1);
    usePredictorStore.getState().clearHistory();
    expect(usePredictorStore.getState().history).toEqual([]);
    expect(usePredictorStore.getState().blue.team_id).toBe('unit-team-blue');
  });
  it('rehydrates a saved draft and result after a page refresh', async () => {
    usePredictorStore.setState(completeFixture());
    usePredictorStore.getState().setResult(analysisFixture()); usePredictorStore.getState().saveRecord();
    const serialized = localStorage.getItem(STORAGE_KEY)!;
    usePredictorStore.getState().resetAll(); usePredictorStore.getState().clearHistory();
    localStorage.setItem(STORAGE_KEY, serialized);
    await usePredictorStore.persist.rehydrate();
    expect(usePredictorStore.getState().blue.team_id).toBe('unit-team-blue');
    expect(usePredictorStore.getState().resultSource).toBe('saved');
    expect(usePredictorStore.getState().history).toHaveLength(1);
  });
  it('ignores malformed local storage instead of crashing or inventing a result', async () => {
    localStorage.setItem(STORAGE_KEY, '{invalid-json');
    await usePredictorStore.persist.rehydrate();
    expect(usePredictorStore.getState().result).toBeNull();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 2, state: { blue: 7, result: { prediction: { blue_win_probability: 0.99 } } } }));
    await usePredictorStore.persist.rehydrate();
    expect(usePredictorStore.getState().result).toBeNull();
  });
  it('loads exact historical names/slots without copying a final outcome into prediction input', () => {
    const original = completeFixture(); original.game_id = 'real-format-unit-fixture';
    usePredictorStore.getState().loadRequest(buildRequest(original), 'Unit historical replay', { blue_team_name: 'Blue observed', red_team_name: 'Red observed', player_names: { 'unit-player-blue-top': 'Observed unit name' } });
    const state = usePredictorStore.getState();
    expect(state.blue.players[0]!.name).toBe('Observed unit name');
    expect(state.blue.team_name).toBe('Blue observed');
    expect(state.blue.roster_status).toBe('exact_historical_game');
    expect(buildRequest(state)).not.toHaveProperty('blue_win');
    expect(state.result).toBeNull();
  });
});
