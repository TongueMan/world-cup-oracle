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
  data_grade: 'A' | 'B' | 'C' | 'D' | 'E';
  confidence_cap: number;
  missing_fields: string[];
  assumptions: string[];
  evidence: PredictionEvidence[];
  probability_components: ProbabilityComponent[];
  applied_adjustments: ProbabilityAdjustment[];
  expected_home_goals: number;
  expected_away_goals: number;
  score_distribution: ScorelineProbability[];
  extra_time_home_win_prob: number;
  extra_time_draw_prob: number;
  extra_time_away_win_prob: number;
  penalty_home_win_prob: number;
  penalty_away_win_prob: number;
  home_advancement_prob: number;
  away_advancement_prob: number;
}

export interface ChampionProbability {
  team_id: string;
  probability: number;
  most_common_eliminator: string;
  potential_key_match: string;
  simulation_count: number;
  probability_source: string;
  is_alive: boolean;
  eliminator_stats: EliminatorStat[];
  key_matchups: KeyMatchupStat[];
}

export interface PredictionEvidence {
  evidence_id: string;
  claim: string;
  source_type: string;
  source_name: string;
  url: string;
  updated_at: string | null;
  freshness: number;
  confidence: number;
  supported_fields: string[];
  conflicts: string[];
  detail?: string;
  affected_team_ids?: string[];
  impact_summary?: string;
  model_usage?: 'applied' | 'model_input' | 'context_only';
}

export interface ProbabilityComponent {
  name: 'market' | 'strength' | 'goals' | 'web_semantic' | 'neutral_prior';
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  confidence: number;
  base_weight: number;
  effective_weight: number;
  evidence_ids: string[];
}

export interface ProbabilityAdjustment {
  factor: string;
  home_delta: number;
  draw_delta: number;
  away_delta: number;
  confidence: number;
  rationale: string;
  evidence_ids: string[];
}

export interface ScorelineProbability {
  home_goals: number;
  away_goals: number;
  probability: number;
}

export interface EliminatorStat {
  opponent_team_id: string;
  round: string;
  elimination_probability: number;
}

export interface KeyMatchupStat {
  opponent_team_id: string;
  round: string;
  encounter_probability: number;
  elimination_probability: number;
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
  artifact_id?: string;
  publication_status?: string;
  data_verified?: boolean;
  prediction: MatchPrediction;
  symbolic_signal: SymbolicSignal | null;
  debate_transcript: DebateTranscript | null;
}

export interface TournamentStateMatch {
  match_id: string;
  stage: string;
  status: string;
  home_team_id: string | null;
  away_team_id: string | null;
  winner_team_id: string | null;
  home_score: number | null;
  away_score: number | null;
  home_penalty: number | null;
  away_penalty: number | null;
  kickoff_time: string | null;
  next_match_id: string | null;
  home_source_match_id: string | null;
  away_source_match_id: string | null;
}

export interface TournamentState {
  requested_anchor: string;
  anchor_label: string;
  as_of_time: string | null;
  active_round: string;
  round_completed: number;
  round_total: number;
  completed_match_ids: string[];
  remaining_match_ids: string[];
  predictable_match_ids: string[];
  alive_teams: string[];
  eliminated_teams: string[];
  locked_results: TournamentStateMatch[];
  remaining_matches: TournamentStateMatch[];
  schedule_snapshot_id: string;
  schedule_hash: string;
  validation_status: 'ready' | 'invalid';
  validation_errors: string[];
  validation_warnings: string[];
}

export interface FeatureModuleStatus {
  enabled: boolean;
  status: 'available' | 'partial' | 'not_connected';
  message: string;
  coverage: number;
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

export interface PredictionReportSection {
  title: string;
  body: string;
  bullets: string[];
  kind?: string;
  citations?: string[];
  figure_refs?: string[];
}

export interface PredictionReportReference {
  reference_id: string;
  label: string;
  source_name: string;
  url: string;
  kind: string;
  note: string;
}

export interface PredictionReportFigure {
  figure_id: string;
  title: string;
  kind: string;
  description: string;
  data?: Record<string, unknown>;
}

export interface TeamFeatures {
  team_id: string;
  team_strength: number;
  normalized_fifa_rank: number;
  normalized_elo: number;
  recent_form: number;
  attack: number;
  defense: number;
  world_cup_experience: number;
  squad_health: number;
  fifa_rank?: number | null;
  elo_rating?: number | null;
  source_key?: string;
  source_url?: string;
}

export interface PredictionAgentReport {
  report_id: string;
  artifact_id: string;
  anchor: string;
  generated_at: string | null;
  status: string;
  headline: string;
  summary: string;
  title?: string;
  abstract?: string;
  methodology_note?: string;
  references?: PredictionReportReference[];
  figures?: PredictionReportFigure[];
  data_disclosure?: string;
  sections: PredictionReportSection[];
  caveats: string[];
  source_artifact_version: string;
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
  artifact_id: string;
  run_id: string;
  publication_status: 'legacy' | 'candidate' | 'published';
  probability_profile: string;
  simulation_count: number;
  input_data_as_of: string | null;
  schedule_snapshot_id: string;
  schedule_hash: string;
  model_config_hash: string;
  current_tournament_state: TournamentState | null;
  feature_modules: Record<string, FeatureModuleStatus>;
  team_features?: TeamFeatures[];
  group_standings: GroupStanding[];
  bracket: Bracket | null;
  match_predictions: MatchPrediction[];
  scenario_match_predictions?: MatchPrediction[];
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
  prediction_report: PredictionAgentReport | null;
  data_verified: boolean;
  data_quality_report: DataQualityReport | null;
}

export interface PredictionSnapshot {
  artifact_id: string;
  generated_at: string | null;
  input_data_as_of: string | null;
  anchor_label: string;
  requested_anchor?: string;
  active_round: string;
  schedule_hash: string;
  simulation_count: number;
  data_verified: boolean;
  publication_status: 'published';
  quality_status: 'ready';
  usable: true;
}

export interface PredictionStageAvailability {
  anchor: string;
  status: 'available' | 'generatable' | 'not_reached' | 'not_captured';
  message: string;
}

export interface PredictionRunResult {
  run_id: string;
  publish_status: 'published' | 'retained_previous' | 'candidate_only';
  reason_codes: string[];
  candidate_artifact_id: string;
  published_artifact_id: string | null;
  artifact: TournamentPrediction;
}

export interface MatchEnvironment {
  match_id?: string;
  data_status?: string;
  reason?: string | null;
  environment_summary?: string | null;
  source?: string | null;
  source_url?: string | null;
  fetched_at?: string | null;
  [key: string]: unknown;
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

export interface WorldCupHistoryEdition {
  year: number;
  name: string;
  name_zh?: string;
  host_countries: string[];
  host_countries_zh?: string[];
  host_flag_codes?: string[];
  champion: string;
  champion_zh?: string;
  champion_flag_code?: string | null;
  runner_up: string;
  runner_up_zh?: string;
  runner_up_flag_code?: string | null;
  match_count: number;
  team_count: number;
  start_date: string | null;
  end_date: string | null;
  source: string;
  source_url: string;
}

export interface WorldCupHistoryMatch {
  match_id: string;
  year: number;
  stage: string;
  stage_zh?: string;
  round: string | null;
  round_zh?: string | null;
  group_name: string | null;
  group_name_zh?: string | null;
  date: string | null;
  time: string | null;
  home_team: string | null;
  home_team_zh?: string | null;
  home_flag_code?: string | null;
  away_team: string | null;
  away_team_zh?: string | null;
  away_flag_code?: string | null;
  home_score: number | null;
  away_score: number | null;
  home_score_et: number | null;
  away_score_et: number | null;
  home_penalty: number | null;
  away_penalty: number | null;
  winner_team: string | null;
  winner_team_zh?: string | null;
  winner_flag_code?: string | null;
  venue: string | null;
  venue_zh?: string | null;
  city: string | null;
  city_zh?: string | null;
  source: string;
  source_url: string;
  champion?: string;
  champion_zh?: string | null;
  champion_flag_code?: string | null;
  runner_up?: string;
  runner_up_zh?: string | null;
  runner_up_flag_code?: string | null;
}

export interface WorldCupHistoryEditionDetail extends WorldCupHistoryEdition {
  stages: string[];
  matches: WorldCupHistoryMatch[];
}

export interface AgentProviderModel {
  id: string;
  label: string;
  mode: string;
}

export interface AgentProviderCapability {
  id: string;
  label: string;
  base_url: string | null;
  custom_base_url: boolean;
  models: AgentProviderModel[];
}

export interface AgentSearchCapability {
  enabled: boolean;
  provider: string | null;
  message: string;
}

export interface AgentCapabilities {
  providers: AgentProviderCapability[];
  search: AgentSearchCapability;
}

export interface AgentLLMConfig {
  provider: string;
  model: string;
  apiKey: string;
  baseURL?: string;
  searchEnabled: boolean;
}

export interface AgentPageContext {
  currentPage?: string;
  activeTab?: string;
  currentMatchId?: string;
  selectedDate?: string;
  summary?: string;
  data?: Record<string, unknown>;
}

export interface AgentChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentSearchResult {
  title: string;
  url: string;
  snippet: string;
  source: string;
  domain?: string;
  publishedAt?: string | null;
  sourceQualityScore?: number;
  relevanceScore?: number;
  sourceType?: string;
  adoptionReason?: string;
  citationId?: number | null;
  excerpt?: string;
}

export interface AgentMatchConfirmation {
  currentMatch?: Record<string, unknown>;
  requestedTeams?: string[];
  candidates?: Array<Record<string, unknown>>;
}

export interface AgentDiagnostics {
  runId?: string | null;
  queryPlan?: Record<string, unknown>;
  searchedCount?: number;
  adoptedCount?: number;
  filteredCount?: number;
  filteredSources?: Array<Record<string, unknown>>;
}

export interface AgentMatchToolResponse {
  answer: string;
  sources: AgentSearchResult[];
  run_id: string | null;
  status?: 'ok' | 'needs_confirmation' | 'local_only' | 'degraded' | 'error';
  confirmation?: AgentMatchConfirmation | null;
  diagnostics?: AgentDiagnostics | null;
  progress?: string[];
  used_search: boolean;
  search_allowed: boolean;
  search_intents: string[];
  missing_local_fields: string[];
  evidence_status: string;
}
