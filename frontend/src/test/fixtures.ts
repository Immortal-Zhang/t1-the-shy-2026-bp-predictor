/** Synthetic structural test fixtures only. Never imported by the application. */
import { initialDraft, ROLES } from '../domain';
import type { AnalyzeResponse, AvailableJudgment, Champion, DraftSnapshot, RosterResponse, TeamSummary } from '../types';

export const TEST_TIME = '2026-10-22T00:00:00Z';
export function completeFixture(): DraftSnapshot {
  const state = initialDraft(TEST_TIME);
  for (const side of ['blue', 'red'] as const) {
    state[side].team_id = `unit-team-${side}`;
    state[side].team_name = `Synthetic ${side} fixture`;
    state[side].players = ROLES.map(role => ({ role, player_id: `unit-player-${side}-${role}`, name: `Fixture ${side} ${role}`, champion: `Unit${side}${role}` }));
  }
  return state;
}

export function analysisFixture(): AnalyzeResponse {
  return {
    prediction: {
      blue_win_probability: 0.63, red_win_probability: 0.37, model_version: 'SYNTHETIC_UNIT_TEST_ONLY', selected_model: 'test',
      as_of: TEST_TIME, scheduled_start: TEST_TIME, model_label_cutoff: '2025-12-30T00:00:00Z',
      data_cutoff: '2026-10-18T00:00:00Z', history_result_available_cutoff: '2026-10-19T00:00:00Z',
      sample_coverage: { history_games: 0, effective_as_of: TEST_TIME, latest_history_game_time: null, latest_history_available_at: null, league_history_games: 0, patch_history_games: 0, unknown_teams: [], unknown_players_in_role: [], unknown_champions_in_role: [], player_champion_games: {}, matchup_games: {}, missing_ban_slots: 10, first_pick_side_observed: false },
      training_samples: {}, first_pick_side: 'unknown', warnings: ['Synthetic unit test only'],
    },
    comparison: { pre_bp: { model: 'test-B', blue_probability: 0.6, red_probability: 0.4 }, post_bp: { model: 'test-C', blue_probability: 0.63, red_probability: 0.37 }, delta_blue: 0.03, limitation: 'Synthetic unit fixture' },
    players: [], matchups: [], synergies: [],
    explanation: { method: 'test-fixture', space: 'raw_log_odds', base_value: 0, raw_prediction: 0, contributions: [], other_contribution: 0, feature_count: 0, notice: 'Synthetic fixture' },
    evaluation: { n: 0, accuracy: 0, roc_auc: null, log_loss: 0, brier_score: 0, ece_10: 0, worlds_target: { n: 0, accuracy: 0, roc_auc: null, log_loss: 0, brier_score: 0, ece_10: 0 }, scope: 'UNIT TEST ONLY', evaluated_data_cutoff: TEST_TIME },
    limitations: ['Synthetic fixture only'], supported_analysis: {},
    draft_context_validation: { enabled: false, rule: null, source_url: null, excluded_champions: [], note: '' },
  };
}

/** Structural fixture for display invariants; never a real prediction. */
export function judgmentFixture(): AvailableJudgment {
  const evidence = (title: string) => ({ title, detail: `Synthetic evidence for ${title}`, category: 'unit_fixture', contribution: -0.1, feature_names: ['unit_feature'], sample_games: 5, evidence_status: 'limited' as const });
  return {
    available: true, version: 'UNIT_METHOD', model_version: 'SYNTHETIC_JUDGMENT_ONLY', engine: 'enhanced',
    winner: { side: 'red', team_id: 'unit-team-red', tie_break: false },
    support: { blue: 22, red: 78, definition: '测试参考集内决策边距的相对位置，不是校准概率。', raw_margin: -0.4, reference_n: 10, out_of_reference_range: false, judgment_calibrated_probability: 0.38 },
    advantage: { key: 'clear', label: '明显倾向', strong_validated: false },
    reasons: [evidence('单元依据甲'), evidence('单元依据乙'), { ...evidence('第3项独立优势尚无证据'), evidence_status: 'unavailable', contribution: null, feature_names: [], sample_games: null }],
    risks: [evidence('单元风险甲'), evidence('单元风险乙')],
    bp_assessment: { favored_side: 'blue', label: 'BP 项支持蓝方', net_contribution: 0.1, weakness: evidence('单元阵容弱点') },
    driver: { primary: 'players_teams', label: '主要依靠选手与战队历史', bp_share: 0.3, players_teams_share: 0.6, context_share: 0.1, note: 'SHAP 绝对贡献份额，不是概率份额。' },
    reliability: { level: 'low', label: '数据可靠性偏低', details: ['Synthetic fixture — no real evidence.'] },
    evaluation: {
      n: 10, accuracy: 0.6, strong: { n: 0, accuracy: null, coverage: 0, wilson_low: null, wilson_high: null },
      grades: [{ key: 'clear', label: '明显倾向', n: 10, accuracy: 0.6, coverage: 1, wilson_low: 0.3, wilson_high: 0.8 }],
      scope: 'SYNTHETIC STRUCTURAL TEST ONLY',
      comparison_note: 'Synthetic fixture; no accuracy improvement claim.',
    },
    limitations: ['Unit fixture only; not experimental evidence.'],
  };
}

export const teamFixture: TeamSummary = { team_id: 'unit-team', name: 'Synthetic team', code: 'UNIT', region: 'TEST', logo_url: null, worlds_2026: false, participation_status: 'unit_fixture', source_url: '' };
export const rosterFixture: RosterResponse = { team_id: 'unit-team', roster_status: 'observed_last_match', observed_at: TEST_TIME, source_url: '', notice: 'Synthetic fixture; not a real roster', players: ROLES.map(role => ({ role, player_id: `unit-player-${role}`, name: `Fixture ${role}`, history_games: 7, recent_games: 7, recent_win_rate: 3 / 7, best_champions: [] })) };
export const championFixtures: Champion[] = [
  { id: 'UnitAlpha', key: '1', name_en: 'Unit Alpha', name_zh: '测试甲', title_zh: '测试法师', image_url: '', tags: ['Mage'], roles: ['mid'] },
  { id: 'UnitBeta', key: '2', name_en: 'Unit Beta', name_zh: '测试乙', title_zh: '测试守护者', image_url: '', tags: ['Tank'], roles: ['top', 'sup'] },
];
