// 与后端 Pydantic schema 对齐的类型定义

export interface GroupStandingRow {
  team_id: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  rank: number;
}

export interface GroupStanding {
  group: string;
  rows: GroupStandingRow[];
}

export interface KnockoutSlot {
  round: string;
  match_id: string;
  home_team_id: string | null;
  away_team_id: string | null;
  home_source: string;
  away_source: string;
  home_score: number | null;
  away_score: number | null;
  winner_team_id: string | null;
  went_to_penalties: boolean;
}

export interface Bracket {
  slots: KnockoutSlot[];
  champion_team_id: string | null;
  runner_up_team_id: string | null;
}

export interface MatchPrediction {
  match_id: string;
  home_team_id: string | null;
  away_team_id: string | null;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  predicted_score: string;
  winner_team_id: string | null;
  confidence: number;
  upset_index: number;
  consensus_type: string;
  reason_codes: string[];
  is_locked_result: boolean;
  source: string;
  extra_time_prob: number;
  penalty_prob: number;
  tactical_summary: string;
  narrative_summary: string;
  symbolic_summary: string;
}

export interface ChampionProbability {
  team_id: string;
  probability: number;
  track: string;
}

export interface TarotSignal {
  home_cards: string[];
  away_cards: string[];
  keywords: string[];
}

export interface IChingSignal {
  gua: string;
  keywords: string[];
  upset_risk: number;
}

export interface AstrologySignal {
  fire_energy: number;
  earth_energy: number;
  air_energy: number;
  water_energy: number;
  keywords: string[];
}

export interface SymbolicSignal {
  match_id: string;
  tarot: TarotSignal | null;
  iching: IChingSignal | null;
  astrology: AstrologySignal | null;
  fortune_score: number;
  symbolic_weight_applied: number;
}

export interface AgentOpinion {
  agent: string;
  support_team_id: string | null;
  confidence: number;
  summary: string;
  detail: string;
  reason_codes: string[];
  cited_signals: string[];
  risk_flags: string[];
}

export interface JudgeDecision {
  winner_team_id: string | null;
  decision_type: string;
  final_confidence: number;
  upset_index: number;
  summary: string;
  final_score: string;
  disagreement_sources: string[];
}

export interface DebateTranscript {
  match_id: string;
  opinions: AgentOpinion[];
  judge_decision: JudgeDecision | null;
}

export interface MatchDetail {
  prediction: MatchPrediction;
  symbolic_signal: SymbolicSignal | null;
  debate_transcript: DebateTranscript | null;
}

export interface DataSourceStatus {
  source_key: string;
  status: string;
  credibility: string;
  fetched_at: string | null;
  records: number;
  message: string;
}

export interface DataQualityReport {
  status: string;
  strict: boolean;
  missing: string[];
  conflicts: Array<Record<string, unknown>>;
  invalid_records: Array<Record<string, unknown>>;
  source_statuses: DataSourceStatus[];
  message: string;
  primary_source?: string;
  knowledge_manifest?: KnowledgeManifest | null;
}

export interface KnowledgeManifest {
  run_id: string;
  source: string;
  source_url: string;
  fetched_at: string;
  raw_dir: string;
  counts: Record<string, number>;
  status: string;
  missing: string[];
  meta: Record<string, unknown>;
}

export interface BingKnowledgeResponse {
  status: string;
  manifest: KnowledgeManifest | null;
  samples: Record<string, Array<Record<string, unknown>>>;
}

export interface TournamentPrediction {
  edition: string;
  seed: number;
  mode: string;
  artifact_version: string;
  generated_at: string | null;
  group_standings: GroupStanding[];
  bracket: Bracket | null;
  match_predictions: MatchPrediction[];
  champion_team_id: string | null;
  runner_up_team_id: string | null;
  semifinalists: string[];
  rational_champion: string | null;
  narrative_champion: string | null;
  symbolic_champion: string | null;
  champion_probabilities: ChampionProbability[];
  upset_alerts: Array<Record<string, unknown>>;
  dark_horses: Array<Record<string, unknown>>;
  data_sources: DataSourceStatus[];
  champion_path: Array<Record<string, unknown>>;
  path_reconstruction_notes: string[];
  debate_transcripts: DebateTranscript[];
  data_verified: boolean;
  data_quality_report: DataQualityReport | null;
}

export interface HealthStatus {
  status: string;
  service: string;
}

export interface WorldCupMatch {
  match_id: string;
  stage: string;
  group_name: string | null;
  kickoff_time: string | null;
  kickoff_label: string | null;
  home_team_id: string | null;
  away_team_id: string | null;
  winner_team_id: string | null;
  home_team_raw: string | null;
  away_team_raw: string | null;
  winner_team_raw: string | null;
  home_score: number | null;
  away_score: number | null;
  home_penalty: number | null;
  away_penalty: number | null;
  status: string;
  next_match_id: string | null;
  source: string;
  source_url: string;
  raw_content_hash: string;
  parser_version: string;
  schema_version: string;
  fetched_at: string | null;
  parse_warnings: string[];
  metadata: Record<string, unknown>;
}

export interface WorldCupSyncStatus {
  last_success_at: string | null;
  last_failed_at: string | null;
  last_status: string;
  source: string;
  fetched_count: number;
  parsed_count: number;
  inserted_count: number;
  updated_count: number;
  error_message: string | null;
  raw_snapshot_dir: string | null;
}

export interface WorldCupStanding {
  id: string;
  group_name: string | null;
  team_id: string | null;
  team_name_raw: string;
  played: number | null;
  won: number | null;
  drawn: number | null;
  lost: number | null;
  goals_for: number | null;
  goals_against: number | null;
  goal_difference: number | null;
  points: number | null;
}

export interface WorldCupPlayerStat {
  category?: string;
  player_name?: string;
  team_name?: string;
  title?: string;
  content?: string;
  value?: number | null;
  image_url?: string | null;
  source_url?: string;
}
