import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { buildRequest, championAvailability, draftSnapshot, emptyTeam, initialDraft, ROLES, validateDraft } from './domain';
import { isJudgment } from './judgment';
import type { AnalyzeResponse, DisplayMode, DraftContext, DraftPlayer, DraftSettings, DraftSnapshot, DraftTeam, HistoryRecord, PredictionRequest, Role, RosterResponse, Side, TeamSummary } from './types';

export const STORAGE_KEY = 'worlds-2026-bp-predictor-v2';
export const STORAGE_VERSION = 2;
export interface ReplayNames { blue_team_name?: string; red_team_name?: string; player_names?: Record<string, string> }
export interface PredictorState extends DraftSnapshot {
  displayMode: DisplayMode;
  setDisplayMode: (mode: DisplayMode) => void;
  result: AnalyzeResponse | null;
  resultSource: 'live' | 'saved' | null;
  history: HistoryRecord[];
  inputRevision: number;
  storageWarning: string | null;
  setSettings: (settings: Partial<DraftSettings>) => void;
  setTeam: (side: Side, team: TeamSummary, roster?: RosterResponse) => void;
  setPlayer: (side: Side, role: Role, player: Pick<DraftPlayer, 'player_id' | 'name'> & Partial<DraftPlayer>) => void;
  setChampion: (side: Side, role: Role, champion: string) => boolean;
  setBan: (side: Side, index: number, champion: string | null) => boolean;
  setSeries: (series: Partial<DraftContext>) => void;
  swapSides: () => void;
  clearBP: () => void;
  resetChampions: () => void;
  resetAll: () => void;
  setResult: (result: AnalyzeResponse | null, expectedRevision?: number) => boolean;
  saveRecord: (matchName?: string) => string | null;
  saveDraft: (matchName?: string) => string;
  loadRecord: (id: string) => void;
  deleteRecord: (id: string) => void;
  clearHistory: () => void;
  setActualResult: (id: string, side: Side | null, source?: 'manual' | 'dataset') => void;
  loadRequest: (request: PredictionRequest, matchName?: string, names?: ReplayNames) => void;
}

const copy = <T,>(value: T): T => structuredClone(value);
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
const finiteProbability = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;

function validResult(value: unknown): value is AnalyzeResponse {
  if (!object(value) || !object(value.prediction)) return false;
  if (value.judgment !== undefined && !isJudgment(value.judgment)) return false;
  const prediction = value.prediction;
  if (!finiteProbability(prediction.blue_win_probability) || !finiteProbability(prediction.red_win_probability) || Math.abs(prediction.blue_win_probability + prediction.red_win_probability - 1) > 1e-6) return false;
  return typeof prediction.model_version === 'string' && typeof prediction.as_of === 'string' &&
    typeof prediction.model_label_cutoff === 'string' && typeof prediction.data_cutoff === 'string' &&
    object(prediction.sample_coverage) && Array.isArray(prediction.warnings) &&
    object(value.comparison) && object(value.comparison.pre_bp) && object(value.comparison.post_bp) &&
    Array.isArray(value.players) && Array.isArray(value.matchups) && Array.isArray(value.synergies) &&
    object(value.explanation) && Array.isArray(value.explanation.contributions) &&
    object(value.evaluation) && object(value.evaluation.worlds_target) && Array.isArray(value.limitations) && object(value.supported_analysis);
}

function validTeam(value: unknown): value is DraftTeam {
  if (!object(value) || typeof value.team_id !== 'string' || typeof value.team_name !== 'string' || !Array.isArray(value.players) || value.players.length !== 5 || !Array.isArray(value.bans) || value.bans.length > 5) return false;
  return ROLES.every(role => value.players instanceof Array && value.players.filter(player => object(player) && player.role === role).length === 1) &&
    value.players.every(player => object(player) && typeof player.player_id === 'string' && typeof player.name === 'string' && typeof player.champion === 'string') && value.bans.every(ban => ban === null || typeof ban === 'string');
}

function validSnapshot(value: unknown): value is DraftSnapshot {
  if (!object(value) || !object(value.settings) || !validTeam(value.blue) || !validTeam(value.red) || !object(value.series)) return false;
  return ['match_name', 'as_of', 'scheduled_start', 'league', 'patch'].every(key => typeof value.settings === 'object' && value.settings !== null && typeof (value.settings as Record<string, unknown>)[key] === 'string') &&
    ['blue', 'red', 'unknown'].includes(String(value.settings.first_pick_side)) && typeof value.settings.worlds_only === 'boolean' &&
    typeof value.series.enabled === 'boolean' && ['bo1', 'bo3', 'bo5'].includes(String(value.series.format)) &&
    Array.isArray(value.series.previous_games) && value.series.previous_games.every(game => object(game) && Array.isArray(game.blue_champions) && Array.isArray(game.red_champions) && [...game.blue_champions, ...game.red_champions].every(champion => typeof champion === 'string'));
}

function validRecord(value: unknown): value is HistoryRecord {
  return object(value) && typeof value.id === 'string' && typeof value.created_at === 'string' && typeof value.match_name === 'string' && typeof value.match_date === 'string' &&
    ['draft', 'prediction'].includes(String(value.recordType)) && validSnapshot(value.snapshot) && (value.result === null || validResult(value.result));
}

function newRecord(state: PredictorState, type: 'draft' | 'prediction', matchName?: string): HistoryRecord {
  const snapshot = draftSnapshot(state);
  if (matchName) snapshot.settings.match_name = matchName;
  return {
    id: crypto.randomUUID(), recordType: type, created_at: new Date().toISOString(),
    match_name: snapshot.settings.match_name || '未命名对局', match_date: snapshot.settings.scheduled_start,
    snapshot, request: type === 'prediction' ? buildRequest(snapshot) : null,
    result: type === 'prediction' && state.result ? copy(state.result) : null,
    actual_result: null, actual_result_source: null,
  };
}

function invalidation(state: PredictorState) {
  return { result: null, resultSource: null, inputRevision: state.inputRevision + 1 };
}

const storage = createJSONStorage(() => ({
  getItem: (name: string) => {
    try {
      const value = localStorage.getItem(name);
      if (value !== null) JSON.parse(value);
      return value;
    } catch {
      try { localStorage.removeItem(name); } catch { /* Browser may deny storage. */ }
      return null;
    }
  },
  setItem: (name: string, value: string) => {
    try { localStorage.setItem(name, value); }
    catch {
      queueMicrotask(() => {
        const warning = '浏览器本地存储不可用或空间不足。当前修改只保留在本页，请勿关闭页面。';
        if (usePredictorStore.getState().storageWarning !== warning) usePredictorStore.setState({ storageWarning: warning });
      });
    }
  },
  removeItem: (name: string) => { try { localStorage.removeItem(name); } catch { /* State remains usable in memory. */ } },
}));

export const usePredictorStore = create<PredictorState>()(persist((set, get) => ({
  displayMode: 'aggressive',
  setDisplayMode: displayMode => set({ displayMode }),
  ...initialDraft(), result: null, resultSource: null, history: [], inputRevision: 0, storageWarning: null,
  setSettings: settings => set(state => {
    const cutoffChanged = settings.as_of !== undefined && Date.parse(settings.as_of) !== Date.parse(state.settings.as_of);
    const resetRoster = (team: DraftTeam): DraftTeam => ({
      ...team, players: team.players.map(player => ({ role: player.role, player_id: '', name: '', champion: player.champion })),
      roster_status: undefined, roster_observed_at: null,
      roster_notice: '信息截止时间已改变，请重新选择战队加载该时点阵容或手动确认选手',
    });
    return { settings: { ...state.settings, ...settings },
      ...(cutoffChanged ? { blue: resetRoster(state.blue), red: resetRoster(state.red) } : {}),
      ...invalidation(state) };
  }),
  setTeam: (side, team, roster) => set(state => ({
    [side]: {
      ...emptyTeam(), team_id: team.team_id, team_name: team.name,
      players: ROLES.map(role => {
        const player = roster?.players.find(value => value.role === role);
        return player ? { ...copy(player), champion: '' } : { role, player_id: '', name: '', champion: '' };
      }),
      roster_status: roster?.roster_status, roster_notice: roster?.notice, roster_observed_at: roster?.observed_at,
    }, game_id: null, ...invalidation(state),
  })),
  setPlayer: (side, role, player) => set(state => ({
    [side]: { ...state[side], players: state[side].players.map(previous => previous.role === role ? { role, champion: previous.champion, ...copy(player) } : previous) },
    game_id: null, ...invalidation(state),
  })),
  setChampion: (side, role, champion) => {
    const state = get();
    if (championAvailability(champion, state, { side, role })) return false;
    set({ [side]: { ...state[side], players: state[side].players.map(player => player.role === role ? { ...player, champion } : player) }, ...invalidation(state) });
    return true;
  },
  setBan: (side, index, champion) => {
    const state = get();
    if (index < 0 || index > 4 || !Number.isInteger(index) || (champion && championAvailability(champion, state, { side, banIndex: index }))) return false;
    const bans = Array.from({ length: 5 }, (_, position) => position === index ? champion : state[side].bans[position] ?? null);
    set({ [side]: { ...state[side], bans }, ...invalidation(state) });
    return true;
  },
  setSeries: series => set(state => ({ series: { ...state.series, ...copy(series) }, ...invalidation(state) })),
  swapSides: () => set(state => ({
    blue: copy(state.red), red: copy(state.blue),
    settings: { ...state.settings, first_pick_side: state.settings.first_pick_side === 'blue' ? 'red' : state.settings.first_pick_side === 'red' ? 'blue' : 'unknown' },
    series: { ...state.series, previous_games: state.series.previous_games.map(game => ({ blue_champions: [...game.red_champions], red_champions: [...game.blue_champions] })) },
    game_id: null, ...invalidation(state),
  })),
  clearBP: () => set(state => ({
    blue: { ...state.blue, players: state.blue.players.map(player => ({ ...player, champion: '' })), bans: Array.from({ length: 5 }, () => null) },
    red: { ...state.red, players: state.red.players.map(player => ({ ...player, champion: '' })), bans: Array.from({ length: 5 }, () => null) },
    ...invalidation(state),
  })),
  resetChampions: () => set(state => ({
    blue: { ...state.blue, players: state.blue.players.map(player => ({ ...player, champion: '' })) },
    red: { ...state.red, players: state.red.players.map(player => ({ ...player, champion: '' })) },
    ...invalidation(state),
  })),
  resetAll: () => set(state => ({ ...initialDraft(), ...invalidation(state) })),
  setResult: (result, expectedRevision) => {
    const state = get();
    if (expectedRevision !== undefined && expectedRevision !== state.inputRevision) return false;
    if (result !== null && !validResult(result)) throw new Error('模型服务返回了无效概率或不完整结果，已拒绝展示。');
    set({ result: result ? copy(result) : null, resultSource: result ? 'live' : null });
    return true;
  },
  saveRecord: matchName => {
    const state = get();
    if (!state.result || validateDraft(state).length) return null;
    const record = newRecord(state, 'prediction', matchName);
    set({ history: [record, ...state.history] });
    return record.id;
  },
  saveDraft: matchName => {
    const state = get();
    const record = newRecord(state, 'draft', matchName);
    set({ history: [record, ...state.history] });
    return record.id;
  },
  loadRecord: id => {
    const state = get();
    const record = state.history.find(item => item.id === id);
    if (!record) return;
    set({ ...copy(record.snapshot), result: record.result ? copy(record.result) : null, resultSource: record.result ? 'saved' : null, inputRevision: state.inputRevision + 1 });
  },
  deleteRecord: id => set(state => ({ history: state.history.filter(record => record.id !== id) })),
  clearHistory: () => set({ history: [] }),
  setActualResult: (id, side, source = 'manual') => set(state => ({ history: state.history.map(record => record.id === id ? { ...record, actual_result: side, actual_result_source: side ? source : null } : record) })),
  loadRequest: (request, matchName, names = {}) => {
    const state = get();
    const team = (side: Side): DraftTeam => ({
      ...emptyTeam(), team_id: request[side].team_id,
      team_name: names[`${side}_team_name`] || request[side].team_id,
      players: ROLES.map(role => {
        const player = request[side].players.find(value => value.role === role);
        return { role, player_id: player?.player_id ?? '', name: names.player_names?.[player?.player_id ?? ''] || player?.player_id || '', champion: player?.champion ?? '' };
      }),
      bans: Array.from({ length: 5 }, (_, index) => request[side].bans[index] ?? null),
      roster_status: 'exact_historical_game', roster_notice: '已加载该场真实比赛的出场名单，不代表当前首发。', roster_observed_at: request.scheduled_start,
    });
    set({
      settings: { ...state.settings, as_of: request.as_of, scheduled_start: request.scheduled_start, league: request.league, patch: request.patch, first_pick_side: request.first_pick_side, match_name: matchName || state.settings.match_name },
      blue: team('blue'), red: team('red'), game_id: request.game_id ?? null,
      series: { enabled: false, format: 'bo1', previous_games: [] }, ...invalidation(state),
    });
  },
}), {
  name: STORAGE_KEY, version: STORAGE_VERSION, storage,
  partialize: state => ({ ...draftSnapshot(state), displayMode: state.displayMode, result: state.result, resultSource: state.resultSource, history: state.history, inputRevision: state.inputRevision }),
  migrate: (persisted, version) => version === STORAGE_VERSION ? persisted : {},
  merge: (persisted, current) => {
    if (!validSnapshot(persisted) || !object(persisted)) return current;
    const result = validResult(persisted.result) ? persisted.result : null;
    return { ...current, ...draftSnapshot(persisted), result, resultSource: result ? 'saved' : null,
      displayMode: ['standard', 'aggressive', 'extreme'].includes(String(persisted.displayMode)) ? persisted.displayMode as DisplayMode : 'aggressive',
      history: Array.isArray(persisted.history) ? persisted.history.filter(validRecord) : [],
      inputRevision: typeof persisted.inputRevision === 'number' ? persisted.inputRevision : 0 };
  },
}));
