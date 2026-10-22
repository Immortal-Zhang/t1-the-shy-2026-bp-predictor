export type Side = 'blue' | 'red';
export type Role = 'top' | 'jng' | 'mid' | 'bot' | 'sup';
export type FirstPickSide = Side | 'unknown';
export type SampleStatus = 'sufficient' | 'limited' | 'none';
export type DisplayMode = 'standard' | 'aggressive' | 'extreme';

export interface Champion {
  id: string;
  key: string;
  name_en: string;
  name_zh: string;
  title_zh: string;
  image_url: string;
  tags: string[];
  roles: Role[];
  role_source?: string;
}
export interface FearlessRules {
  verified: boolean;
  fearless_mode: 'global' | null;
  source_url: string;
  description: string;
  applicability?: string;
  [key: string]: unknown;
}
export interface CatalogResponse {
  champions: Champion[];
  worlds: { rules: FearlessRules; [key: string]: unknown };
  provenance: Record<string, unknown>;
}
export interface TeamSummary {
  team_id: string;
  name: string;
  code: string;
  region: string;
  logo_url: string | null;
  worlds_2026: boolean;
  participation_status: string;
  source_url: string;
  logo_source?: string | null;
}
export interface ChampionHistory { champion: string; games: number; win_rate: number | null }
export interface RosterPlayer {
  role: Role;
  player_id: string;
  name: string;
  history_games: number;
  recent_games: number;
  recent_win_rate: number | null;
  best_champions: ChampionHistory[];
}
export interface RosterResponse {
  team_id: string;
  roster_status: string;
  observed_at: string | null;
  source_url: string;
  notice: string;
  players: RosterPlayer[];
}
export interface TeamResponse { teams: TeamSummary[]; [key: string]: unknown }
export interface PlayerLookup {
  player_id: string;
  alias: string;
  identity_basis: string;
  first_observed: string;
}
export interface PlayersResponse { players: PlayerLookup[]; as_of: string; returned: number; identity_notice: string }
export interface RequestPlayer { role: Role; player_id: string; champion: string }
export interface RequestTeam { team_id: string; players: RequestPlayer[]; bans: (string | null)[] }
export interface PredictionRequest {
  as_of: string;
  scheduled_start: string;
  league: string;
  patch: string;
  blue: RequestTeam;
  red: RequestTeam;
  first_pick_side: FirstPickSide;
  game_id?: string | null;
}
export interface PreviousGame { blue_champions: string[]; red_champions: string[] }
export interface DraftContext { enabled: boolean; format: 'bo1' | 'bo3' | 'bo5'; previous_games: PreviousGame[] }
export interface AnalysisRequest extends PredictionRequest { draft_context?: DraftContext }
export interface HistoricalMatch {
  game_id: string;
  date: string;
  league: string;
  patch: string;
  blue_team_id: string;
  blue_team_name: string;
  red_team_id: string;
  red_team_name: string;
  blue_win: number;
  request: PredictionRequest;
  player_names?: Record<string, string>;
}
export interface MatchesResponse { matches: HistoricalMatch[]; [key: string]: unknown }
export interface ModelStatus {
  available: boolean;
  reason?: string;
  label_cutoff?: string;
  model_version?: string;
  integrity?: string;
  note?: string;
}
export interface PatchVerification {
  status: 'confirmed' | 'unverified' | 'mismatch';
  configured_patch: string;
  official_patch?: string;
  checked_at?: string;
  reason?: string;
  official_source?: string;
  [key: string]: unknown;
}
export interface HealthResponse {
  service: string;
  model: ModelStatus;
  worlds_patch_verification: PatchVerification;
  series_prediction_supported: boolean;
}
export interface SampleCoverage {
  history_games: number;
  effective_as_of: string;
  latest_history_game_time: string | null;
  latest_history_available_at: string | null;
  league_history_games: number;
  patch_history_games: number;
  unknown_teams: string[];
  unknown_players_in_role: string[];
  unknown_champions_in_role: string[];
  player_champion_games: Record<string, number>;
  matchup_games: Record<string, number>;
  missing_ban_slots: number;
  first_pick_side_observed: boolean;
  [key: string]: unknown;
}
export interface PredictionResponse {
  blue_win_probability: number;
  red_win_probability: number;
  model_version: string;
  selected_model: string;
  as_of: string;
  scheduled_start: string;
  model_label_cutoff: string;
  data_cutoff: string;
  history_result_available_cutoff: string;
  sample_coverage: SampleCoverage;
  training_samples: Record<string, unknown>;
  first_pick_side: FirstPickSide;
  warnings: string[];
  input_league?: string;
  model_league?: string;
  input_patch?: string;
  model_patch?: string;
  patch_namespace_note?: string;
  worlds_patch_verification?: PatchVerification;
}
export interface ProbabilityModel { model: string; blue_probability: number; red_probability: number }
export interface PlayerAnalysis {
  side: Side;
  role: Role;
  player_id: string;
  name: string;
  champion: string;
  games: number;
  wins: number;
  win_rate: number | null;
  last_played: string | null;
  recent_games: number;
  recent_win_rate: number | null;
  player_history_games: number;
  player_recent_win_rate: number | null;
  sample_status: SampleStatus;
}
export interface MatchupAnalysis {
  role: Role;
  blue_champion: string;
  red_champion: string;
  games: number;
  blue_win_rate: number | null;
  sample_status: SampleStatus;
}
export interface SynergyAnalysis {
  side: Side;
  champions: [string, string];
  roles: [Role, Role];
  games: number;
  win_rate: number | null;
  sample_status: SampleStatus;
}
export interface MetricSummary {
  n: number;
  accuracy: number;
  roc_auc: number | null;
  log_loss: number;
  brier_score: number;
  ece_10: number;
}
export interface FeatureContribution { feature: string; label: string; value: string | number; contribution: number }
export interface JudgmentEvidence {
  title: string;
  detail: string;
  category: string;
  contribution: number | null;
  feature_names: string[];
  sample_games: number | null;
  evidence_status: 'model' | 'limited' | 'unavailable';
}
export interface JudgmentGradePerformance {
  key: string;
  label: string;
  n: number;
  accuracy: number | null;
  coverage: number;
  wilson_low: number | null;
  wilson_high: number | null;
}
export interface AvailableJudgment {
  available: true;
  version: string;
  model_version: string;
  engine: 'enhanced' | 'frozen';
  winner: { side: Side; team_id: string; tie_break: boolean };
  support: {
    blue: number; red: number; definition: string; raw_margin: number; reference_n: number;
    out_of_reference_range: boolean; judgment_calibrated_probability: number;
  };
  advantage: { key: 'slight' | 'clear' | 'strong'; label: string; strong_validated: boolean };
  reasons: JudgmentEvidence[];
  risks: JudgmentEvidence[];
  bp_assessment: { favored_side: Side | null; label: string; net_contribution: number; weakness: JudgmentEvidence };
  driver: { primary: 'bp' | 'players_teams' | 'context'; label: string; bp_share: number; players_teams_share: number; context_share: number; note: string };
  reliability: { level: 'low' | 'medium' | 'high'; label: string; details: string[] };
  evaluation: {
    n: number; accuracy: number;
    strong: { n: number; accuracy: number | null; coverage: number; wilson_low: number | null; wilson_high: number | null };
    grades: JudgmentGradePerformance[];
    scope: string;
    comparison_note: string;
  };
  limitations: string[];
}
export type Judgment = AvailableJudgment | { available: false; reason: string };
export interface AnalyzeResponse {
  judgment?: Judgment;
  prediction: PredictionResponse;
  comparison: { pre_bp: ProbabilityModel; post_bp: ProbabilityModel; delta_blue: number; limitation: string };
  players: PlayerAnalysis[];
  matchups: MatchupAnalysis[];
  synergies: SynergyAnalysis[];
  explanation: {
    method: string;
    space: 'raw_log_odds';
    base_value: number;
    raw_prediction: number;
    contributions: FeatureContribution[];
    other_contribution: number;
    feature_count: number;
    notice: string;
  };
  evaluation: MetricSummary & { worlds_target: MetricSummary; scope: string; evaluated_data_cutoff: string };
  limitations: string[];
  supported_analysis: Record<string, { available: boolean; kind: string; description: string }>;
  draft_context_validation: { enabled: boolean; rule: string | null; source_url: string | null; excluded_champions: string[]; note: string };
}
export interface DraftSettings {
  match_name: string;
  as_of: string;
  scheduled_start: string;
  league: string;
  patch: string;
  first_pick_side: FirstPickSide;
  worlds_only: boolean;
}
export interface DraftPlayer {
  role: Role;
  player_id: string;
  name: string;
  champion: string;
  history_games?: number;
  recent_games?: number;
  recent_win_rate?: number | null;
  best_champions?: ChampionHistory[];
}
export interface DraftTeam {
  team_id: string;
  team_name: string;
  players: DraftPlayer[];
  bans: (string | null)[];
  roster_status?: string;
  roster_notice?: string;
  roster_observed_at?: string | null;
}
export interface DraftSnapshot {
  settings: DraftSettings;
  blue: DraftTeam;
  red: DraftTeam;
  series: DraftContext;
  game_id?: string | null;
}
export interface HistoryRecord {
  id: string;
  recordType: 'draft' | 'prediction';
  created_at: string;
  match_name: string;
  match_date: string;
  snapshot: DraftSnapshot;
  request: AnalysisRequest | null;
  result: AnalyzeResponse | null;
  actual_result: Side | null;
  actual_result_source: 'manual' | 'dataset' | null;
}

export type MatchSummary = HistoricalMatch;
export type PlayerDraft = DraftPlayer;
