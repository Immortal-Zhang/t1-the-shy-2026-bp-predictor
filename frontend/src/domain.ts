import type { AnalysisRequest, Champion, DraftContext, DraftSnapshot, DraftTeam, Role, Side } from './types';

export const ROLES: Role[] = ['top', 'jng', 'mid', 'bot', 'sup'];
export const ROLE_LABELS: Record<Role, string> = { top: 'TOP', jng: 'JUNGLE', mid: 'MID', bot: 'BOT', sup: 'SUPPORT' };
export const ROLE_NAMES: Record<Role, string> = { top: '上路', jng: '打野', mid: '中路', bot: '下路', sup: '辅助' };
export const SIDES: Side[] = ['blue', 'red'];

export function parseApiDate(value: string): Date {
  return new Date(value.replace(/^(\d{4}-\d{2}-\d{2}) /, '$1T'));
}

export function emptyTeam(): DraftTeam {
  return { team_id: '', team_name: '', players: ROLES.map(role => ({ role, player_id: '', name: '', champion: '' })), bans: Array.from({ length: 5 }, () => null) };
}

export function initialDraft(now = new Date().toISOString()): DraftSnapshot {
  return {
    settings: { match_name: '未命名对局', as_of: now, scheduled_start: now, league: 'Worlds', patch: '26.20', first_pick_side: 'unknown', worlds_only: true },
    blue: emptyTeam(), red: emptyTeam(),
    series: { enabled: false, format: 'bo1', previous_games: [] },
    game_id: null,
  };
}

export function draftSnapshot(value: DraftSnapshot): DraftSnapshot {
  return structuredClone({ settings: value.settings, blue: value.blue, red: value.red, series: value.series, game_id: value.game_id ?? null });
}

export function blockedChampions(series: DraftContext): string[] {
  return series.enabled ? [...new Set(series.previous_games.flatMap(game => [...game.blue_champions, ...game.red_champions]).filter(Boolean))] : [];
}

export interface SelectionTarget { side: Side; role?: Role; banIndex?: number }

export function championAvailability(champion: string, draft: DraftSnapshot, target?: SelectionTarget): string | null {
  if (!champion) return null;
  const name = champion.toLocaleLowerCase();
  if (blockedChampions(draft.series).some(value => value.toLocaleLowerCase() === name)) return 'Fearless：前序小局已经使用';
  for (const side of SIDES) {
    for (const player of draft[side].players) {
      if (target?.side === side && target.role === player.role) continue;
      if (player.champion.toLocaleLowerCase() === name) return '已被选择';
    }
    for (const [index, ban] of draft[side].bans.entries()) {
      if (target?.side === side && target.banIndex === index) continue;
      if (ban?.toLocaleLowerCase() === name) return '已被禁用';
    }
  }
  return null;
}

export function searchChampions(champions: Champion[], search: string, role?: Role | 'all'): Champion[] {
  const query = search.trim().toLocaleLowerCase();
  return champions.filter(champion => (!role || role === 'all' || champion.roles.includes(role)) &&
    (!query || [champion.id, champion.name_en, champion.name_zh, champion.title_zh].some(value => value.toLocaleLowerCase().includes(query))));
}

export function validateDraft(draft: DraftSnapshot, fearlessRuleVerified = true): string[] {
  const errors: string[] = [];
  const { settings } = draft;
  if (!draft.blue.team_id || !draft.red.team_id) errors.push('请先选择蓝红双方战队');
  if (draft.blue.team_id && draft.blue.team_id.toLocaleLowerCase() === draft.red.team_id.toLocaleLowerCase()) errors.push('蓝红双方不能是同一支战队');
  const picks: string[] = [];
  const players: string[] = [];
  for (const side of SIDES) {
    const team = draft[side];
    const label = side === 'blue' ? '蓝方' : '红方';
    if (team.roster_observed_at && parseApiDate(team.roster_observed_at).valueOf() > parseApiDate(settings.as_of).valueOf()) errors.push(`${label}阵容观测晚于信息截止时间，请重新选择战队并核对选手`);
    if (team.players.length !== 5 || new Set(team.players.map(player => player.role)).size !== 5 || ROLES.some(role => !team.players.some(player => player.role === role))) errors.push(`${label}必须拥有五个不同位置`);
    for (const player of team.players) {
      if (!player.player_id.trim()) errors.push(`${label} ${ROLE_LABELS[player.role]} 缺少职业选手`);
      else players.push(player.player_id.toLocaleLowerCase());
      if (!player.champion.trim()) errors.push(`${label} ${ROLE_LABELS[player.role]} 尚未选择英雄`);
      else picks.push(player.champion.toLocaleLowerCase());
    }
    if (team.bans.length > 5) errors.push(`${label}最多五个禁用英雄`);
  }
  if (new Set(players).size !== players.length) errors.push('同一名选手不能占据多个位置');
  if (new Set(picks).size !== picks.length) errors.push('同一局不能重复选择英雄');
  const bans = [...draft.blue.bans, ...draft.red.bans].filter((value): value is string => Boolean(value)).map(value => value.toLocaleLowerCase());
  if (new Set(bans).size !== bans.length) errors.push('不能重复禁用同一英雄');
  if (picks.some(value => bans.includes(value))) errors.push('已禁用的英雄不能被选择');
  if (!/^\d{2}\.\d{1,2}$/.test(settings.patch)) errors.push('请输入有效比赛版本，例如 26.20');
  if (!settings.league.trim()) errors.push('请填写联赛名称');
  const asOf = Date.parse(settings.as_of), start = Date.parse(settings.scheduled_start);
  if (!Number.isFinite(asOf) || !Number.isFinite(start)) errors.push('请输入有效的赛前截止时间和比赛时间');
  else if (asOf > start) errors.push('数据截止时间不能晚于比赛开始时间');
  if (draft.series.enabled) {
    if (!fearlessRuleVerified) errors.push('官方 Fearless 规则尚未核验，暂不能启用');
    if (draft.series.format === 'bo1') errors.push('Fearless 上下文需要选择 Bo3 或 Bo5');
    const maximum = draft.series.format === 'bo3' ? 2 : 4;
    if (draft.series.previous_games.length > maximum) errors.push('前序小局数量超过当前系列赛格式');
    const prior = draft.series.previous_games.flatMap(game => [...game.blue_champions, ...game.red_champions]).filter(Boolean);
    if (draft.series.previous_games.some(game => game.blue_champions.length !== 5 || game.red_champions.length !== 5 || [...game.blue_champions, ...game.red_champions].some(champion => !champion))) errors.push('每个前序小局须记录双方完整十个英雄');
    if (new Set(prior.map(champion => champion.toLocaleLowerCase())).size !== prior.length) errors.push('前序 Fearless 小局不能重复使用英雄');
    const forbidden = new Set(blockedChampions(draft.series).map(champion => champion.toLocaleLowerCase()));
    if (picks.some(champion => forbidden.has(champion))) errors.push('当前阵容包含 Fearless 已使用英雄');
  }
  return [...new Set(errors)];
}

export function buildRequest(draft: DraftSnapshot): AnalysisRequest {
  const team = (side: Side) => ({
    team_id: draft[side].team_id,
    players: ROLES.map(role => {
      const player = draft[side].players.find(value => value.role === role);
      return { role, player_id: player?.player_id ?? '', champion: player?.champion ?? '' };
    }),
    bans: [...draft[side].bans],
  });
  return {
    as_of: draft.settings.as_of, scheduled_start: draft.settings.scheduled_start,
    league: draft.settings.league, patch: draft.settings.patch,
    first_pick_side: draft.settings.first_pick_side,
    blue: team('blue'), red: team('red'),
    ...(draft.game_id ? { game_id: draft.game_id } : {}),
    draft_context: structuredClone(draft.series),
  };
}

export function sortedHistory<T extends { match_date: string; created_at: string }>(history: T[]): T[] {
  return [...history].sort((a, b) => Date.parse(b.match_date) - Date.parse(a.match_date) || Date.parse(b.created_at) - Date.parse(a.created_at));
}
