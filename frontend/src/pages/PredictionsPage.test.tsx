import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TournamentPrediction } from '../lib/types';
import PredictionsPage from './PredictionsPage';

vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: { series?: Array<{ type?: string }> } }) => (
    <div data-chart-type={option.series?.[0]?.type ?? 'unknown'} data-testid="echarts" />
  ),
}));

const semifinalPredictions = [
  {
    match_id: 'SF-1',
    home_team_id: 'FRA',
    away_team_id: 'ESP',
    home_win_prob: 0.41,
    draw_prob: 0.24,
    away_win_prob: 0.35,
    predicted_score: '1-1',
    winner_team_id: 'FRA',
    confidence: 0.65,
    upset_index: 0,
    consensus_type: 'multi_source_fusion',
    reason_codes: ['balanced_matchup'],
    is_locked_result: false,
    source: 'multi_source_fusion',
    extra_time_prob: 0.24,
    penalty_prob: 0.09,
    tactical_summary: '',
    narrative_summary: '',
    symbolic_summary: '',
    data_grade: 'C',
    confidence_cap: 0.65,
    missing_fields: ['market_odds', 'confirmed_lineup_or_injuries'],
    assumptions: [],
    evidence: [],
    probability_components: [
      { name: 'strength', home_win_prob: 0.43, draw_prob: 0.22, away_win_prob: 0.35, confidence: 0.75, base_weight: 0.4, effective_weight: 0.53, evidence_ids: [] },
      { name: 'goals', home_win_prob: 0.41, draw_prob: 0.25, away_win_prob: 0.34, confidence: 0.68, base_weight: 0.25, effective_weight: 0.3, evidence_ids: [] },
    ],
    applied_adjustments: [],
    expected_home_goals: 1.5,
    expected_away_goals: 1.36,
    score_distribution: [
      { home_goals: 1, away_goals: 1, probability: 0.116 },
      { home_goals: 2, away_goals: 1, probability: 0.088 },
    ],
    extra_time_home_win_prob: 0.33,
    extra_time_draw_prob: 0.38,
    extra_time_away_win_prob: 0.29,
    penalty_home_win_prob: 0.5,
    penalty_away_win_prob: 0.5,
    home_advancement_prob: 0.54,
    away_advancement_prob: 0.46,
  },
  {
    match_id: 'SF-2',
    home_team_id: 'ENG',
    away_team_id: 'ARG',
    home_win_prob: 0.32,
    draw_prob: 0.23,
    away_win_prob: 0.45,
    predicted_score: '1-1',
    winner_team_id: 'ARG',
    confidence: 0.65,
    upset_index: 0,
    consensus_type: 'multi_source_fusion',
    reason_codes: ['balanced_matchup'],
    is_locked_result: false,
    source: 'multi_source_fusion',
    extra_time_prob: 0.23,
    penalty_prob: 0.09,
    tactical_summary: '',
    narrative_summary: '',
    symbolic_summary: '',
    data_grade: 'C',
    confidence_cap: 0.65,
    missing_fields: ['market_odds', 'confirmed_lineup_or_injuries'],
    assumptions: [],
    evidence: [],
    probability_components: [
      { name: 'strength', home_win_prob: 0.3, draw_prob: 0.21, away_win_prob: 0.49, confidence: 0.75, base_weight: 0.4, effective_weight: 0.53, evidence_ids: [] },
    ],
    applied_adjustments: [],
    expected_home_goals: 1.32,
    expected_away_goals: 1.57,
    score_distribution: [{ home_goals: 1, away_goals: 1, probability: 0.115 }],
    extra_time_home_win_prob: 0.28,
    extra_time_draw_prob: 0.38,
    extra_time_away_win_prob: 0.35,
    penalty_home_win_prob: 0.5,
    penalty_away_win_prob: 0.5,
    home_advancement_prob: 0.43,
    away_advancement_prob: 0.57,
  },
] as const;

const baseArtifact = {
  artifact_id: 'published-1',
  run_id: 'run-1',
  publication_status: 'published',
  artifact_version: '4.0.0',
  generated_at: '2026-07-14T00:10:00Z',
  input_data_as_of: '2026-07-14T00:00:00Z',
  simulation_count: 10_000,
  seed: 42,
  mode: 'professional',
  probability_profile: 'professional',
  schedule_snapshot_id: 'schedule-1',
  schedule_hash: 'hash',
  model_config_hash: 'model-hash',
  current_tournament_state: {
    requested_anchor: 'current',
    anchor_label: '当前四强阶段',
    as_of_time: '2026-07-14T00:00:00Z',
    active_round: 'SF',
    round_completed: 0,
    round_total: 2,
    completed_match_ids: ['QF-1', 'QF-2', 'QF-3', 'QF-4'],
    remaining_match_ids: ['SF-1', 'SF-2', 'FINAL'],
    predictable_match_ids: ['SF-1', 'SF-2'],
    alive_teams: ['ARG', 'ENG', 'ESP', 'FRA'],
    eliminated_teams: [],
    locked_results: [],
    remaining_matches: [],
    schedule_snapshot_id: 'schedule-1',
    schedule_hash: 'hash',
    validation_status: 'ready',
    validation_errors: [],
    validation_warnings: [],
  },
  champion_probabilities: [
    { team_id: 'ARG', probability: 0.34, most_common_eliminator: 'FRA', potential_key_match: 'ARG vs FRA', simulation_count: 10_000, probability_source: 'conditional_monte_carlo', is_alive: true, eliminator_stats: [], key_matchups: [] },
    { team_id: 'FRA', probability: 0.29, most_common_eliminator: 'ARG', potential_key_match: 'FRA vs ARG', simulation_count: 10_000, probability_source: 'conditional_monte_carlo', is_alive: true, eliminator_stats: [], key_matchups: [] },
    { team_id: 'ENG', probability: 0.21, most_common_eliminator: 'BRA', potential_key_match: 'ENG vs BRA', simulation_count: 10_000, probability_source: 'conditional_monte_carlo', is_alive: true, eliminator_stats: [], key_matchups: [] },
    { team_id: 'ESP', probability: 0.16, most_common_eliminator: 'ENG', potential_key_match: 'ESP vs ENG', simulation_count: 10_000, probability_source: 'conditional_monte_carlo', is_alive: true, eliminator_stats: [], key_matchups: [] },
  ],
  match_predictions: semifinalPredictions,
  feature_modules: {
    strength: { enabled: true, status: 'available', message: '球队实力已接入', coverage: 1 },
    goals: { enabled: true, status: 'available', message: '进球模型已接入', coverage: 1 },
    market: { enabled: false, status: 'not_connected', message: '本次预测未使用赔率。', coverage: 0 },
  },
  data_verified: true,
  data_quality_report: { status: 'ready', strict: true, missing: [], conflicts: [], invalid_records: [], source_statuses: [], message: 'ready' },
  group_standings: [],
  bracket: null,
  match_results: [],
  champion_team_id: null,
  runner_up_team_id: null,
  semifinalists: [],
  rational_champion: 'ARG',
  narrative_champion: null,
  symbolic_champion: null,
  narratives: [],
  symbolic_signals: [],
  debate_transcripts: [],
  reasoning_traces: [],
  upset_alerts: [],
  dark_horses: [],
  data_sources: [],
  champion_path: [],
  path_reconstruction_notes: [],
  prediction_report: {
    report_id: 'report-1',
    artifact_id: 'published-1',
    anchor: 'current',
    generated_at: '2026-07-14T00:10:00Z',
    status: 'generated',
    headline: '阿根廷暂居冠军概率首位，估计夺冠概率 34.0%',
    summary: '基于截至 2026-07-14 的赛程与可用证据，阿根廷暂居冠军概率首位。',
    title: '2026 世界杯四强阶段冠军概率预测报告',
    abstract: '基于截至 2026-07-14 的赛程与可用证据，阿根廷暂居冠军概率首位，主要竞争者包括法国、英格兰和巴西。',
    methodology_note: '所有概率均基于当前输入快照生成。',
    references: [
      { reference_id: 'model-1', label: '本地赛程与模型输出', source_name: '世界杯预测系统', url: '', kind: 'model', note: '赛程状态、单场概率和路径模拟。' },
    ],
    figures: [
      { figure_id: 'champion_probability_chart', title: '冠军概率分布', kind: 'echarts', description: '冠军概率榜。' },
    ],
    data_disclosure: '当前质量报告未列出阻断性缺失；实时来源仍可能随赛前信息变化。',
    sections: [
      { title: '预测结论', body: '阿根廷暂居冠军概率首位，估计夺冠概率为 34.0%。', bullets: ['预测起点：当前四强阶段'], kind: 'summary', citations: ['model-1'], figure_refs: ['champion_probability_chart'] },
      { title: '证据与数据来源', body: '本次报告综合使用本地赛程、模型输出和已通过来源准入的数据模块。', bullets: ['球队实力和进球模型已进入概率。'], kind: 'evidence', citations: ['model-1'], figure_refs: [] },
    ],
    caveats: ['概率不是确定赛果。', '不构成投注建议。'],
    source_artifact_version: '4.0.0',
  },
} as unknown as TournamentPrediction;

const apiMock = vi.hoisted(() => ({
  getTournament: vi.fn(),
  getPredictionCandidate: vi.fn(),
  getPredictionSnapshots: vi.fn(),
  getPredictionStages: vi.fn(),
  getWorldCupMatches: vi.fn(),
  getWorldCupSyncStatus: vi.fn(),
  getPredictionSnapshot: vi.fn(),
  syncWorldCup: vi.fn(),
  runFullPrediction: vi.fn(),
  getMatchEnvironment: vi.fn(),
}));

vi.mock('../lib/api', () => ({ api: apiMock }));

describe('PredictionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getTournament.mockResolvedValue(baseArtifact);
    apiMock.getPredictionCandidate.mockRejectedValue(new Error('no candidate'));
    apiMock.getPredictionSnapshots.mockResolvedValue([]);
    apiMock.getPredictionStages.mockResolvedValue([
      { anchor: 'current', status: 'available', message: '该阶段已保存正式预测报告。' },
    ]);
    apiMock.getWorldCupMatches.mockResolvedValue([
      { match_id: 'QF-1', stage: 'QF', status: 'complete', home_team_id: 'ARG', away_team_id: 'BRA', winner_team_id: 'ARG', kickoff_time: '2026-07-12T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'QF-2', stage: 'QF', status: 'complete', home_team_id: 'ENG', away_team_id: 'GER', winner_team_id: 'ENG', kickoff_time: '2026-07-12T22:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'QF-3', stage: 'QF', status: 'complete', home_team_id: 'FRA', away_team_id: 'POR', winner_team_id: 'FRA', kickoff_time: '2026-07-13T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'QF-4', stage: 'QF', status: 'complete', home_team_id: 'ESP', away_team_id: 'NED', winner_team_id: 'ESP', kickoff_time: '2026-07-13T22:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'SF-1', stage: 'SF', status: 'scheduled', home_team_id: 'FRA', away_team_id: 'ESP', kickoff_time: '2026-07-14T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'SF-2', stage: 'SF', status: 'scheduled', home_team_id: 'ENG', away_team_id: 'ARG', kickoff_time: '2026-07-15T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'FINAL', stage: 'Final', status: 'scheduled', home_team_id: 'W101', away_team_id: 'TBD', kickoff_time: '2026-07-20T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
    ]);
    apiMock.getWorldCupSyncStatus.mockResolvedValue({ last_status: 'success' });
    apiMock.runFullPrediction.mockResolvedValue({ publish_status: 'published', artifact: baseArtifact });
  });

  it('renders a readable default champion report instead of an empty panel', async () => {
    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    expect(await screen.findByText(/阿根廷 暂居冠军概率首位/)).toBeInTheDocument();
    expect(screen.getAllByText('34.0%').length).toBeGreaterThan(0);
    expect(screen.getByText('冠军概率排行榜')).toBeInTheDocument();
    expect(screen.getByText('预测结论')).toBeInTheDocument();
    expect(screen.getByText('参考来源')).toBeInTheDocument();
    expect(screen.getAllByText('完整预测').length).toBeGreaterThan(0);
    expect(screen.getByTestId('echarts')).toHaveAttribute('data-chart-type', 'pie');
    expect(screen.queryByRole('button', { name: '进决赛' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '进四强' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '进八强' })).not.toBeInTheDocument();
  });

  it('rejects an old cached report instead of rebuilding public reasoning in the browser', async () => {
    apiMock.getTournament.mockResolvedValue({
      ...baseArtifact,
      prediction_report: {
        report_id: 'legacy-report',
        artifact_id: 'wc2026-old',
        anchor: 'post_qf',
        generated_at: '2026-07-14T00:10:00Z',
        status: 'generated',
        headline: '当前模型最看好 阿根廷 夺冠，夺冠概率 30.5%',
        summary: '本报告状态为透明试算，由 artifact wc2026-old 的结构化概率生成。',
        sections: [
          { title: '结论摘要', body: '本报告状态为透明试算，由 artifact wc2026-old 的结构化概率生成。', bullets: [] },
        ],
        caveats: [],
        source_artifact_version: '4.0.0',
      },
    } as unknown as TournamentPrediction);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    expect(await screen.findByText('本次预测暂缺正式解读')).toBeInTheDocument();
    expect(screen.getByText(/页面不会自行补写理由或引用旧报告/)).toBeInTheDocument();
    expect(screen.queryByText(/artifact wc2026-old/)).not.toBeInTheDocument();
    expect(screen.queryByText(/透明试算/)).not.toBeInTheDocument();
    expect(screen.queryByText(/当前模型最看好/)).not.toBeInTheDocument();
  });

  it('supports stage switching and states the historical information boundary', async () => {
    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    const select = await screen.findByLabelText('预测起点');
    fireEvent.change(select, { target: { value: 'post_qf' } });

    expect(screen.getAllByText('8 强后 / 4 强赛前').length).toBeGreaterThan(0);
    await waitFor(() => expect(apiMock.getTournament).toHaveBeenCalledWith('post_qf'));
    await waitFor(() => expect(apiMock.getPredictionCandidate).toHaveBeenCalledWith('post_qf'));
  });

  it('disables generation for an unsupported prediction start', async () => {
    apiMock.getPredictionStages.mockResolvedValue([
      { anchor: 'current', status: 'available', message: '该阶段已保存正式预测报告。' },
      { anchor: 'pre_tournament', status: 'not_captured', message: '赛前预测需要完整小组赛模拟。' },
    ]);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    const select = await screen.findByLabelText('预测起点');
    fireEvent.change(select, { target: { value: 'pre_tournament' } });

    await waitFor(() => expect(apiMock.getTournament).toHaveBeenCalledWith('pre_tournament'));
    expect(screen.getByRole('button', { name: /重新模拟/ })).toBeDisabled();
  });

  it('does not display an unverified candidate as a champion prediction', async () => {
    const trial = {
      ...baseArtifact,
      publication_status: 'candidate',
      data_verified: false,
      data_quality_report: {
        status: 'degraded_prediction',
        strict: true,
        missing: ['market_odds', 'missing_required_model_fields'],
        conflicts: [],
        invalid_records: [],
        source_statuses: [],
        message: 'data coverage is incomplete; show as a basic prediction version.',
      },
    } as unknown as TournamentPrediction;
    apiMock.getTournament.mockRejectedValue(new Error('{"status":"invalid","invalid_records":[{"reason":"missing_required_model_fields"}]}'));
    apiMock.getPredictionCandidate.mockResolvedValue(trial);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    expect(await screen.findByText('当前没有有效冠军预测')).toBeInTheDocument();
    expect(screen.queryByText('34.0%')).not.toBeInTheDocument();
    expect(screen.queryByText(/阿根廷 暂居冠军概率首位/)).not.toBeInTheDocument();
    expect(screen.queryByText(/invalid_records/)).not.toBeInTheDocument();
    expect(screen.queryByText(/missing_required_model_fields/)).not.toBeInTheDocument();
  });

  it('explains the real data blocker and keeps developer diagnostics collapsed', async () => {
    const unavailable = {
      ...baseArtifact,
      artifact_id: 'unavailable-current',
      publication_status: 'candidate',
      data_verified: false,
      champion_probabilities: [],
      match_predictions: [],
      prediction_report: null,
      data_quality_report: {
        status: 'data_unavailable',
        strict: true,
        missing: ['verified_team_model_features_unavailable', 'alive_team_features_missing', 'champion_probabilities_empty'],
        conflicts: [],
        invalid_records: [],
        source_statuses: [],
        message: 'internal diagnostic text',
      },
    } as unknown as TournamentPrediction;
    apiMock.getTournament.mockRejectedValue(new Error('no verified prediction'));
    apiMock.getPredictionCandidate.mockResolvedValue(unavailable);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole('button', { name: '模型与数据' }));
    expect(await screen.findByText(/真实模型特征尚未补齐，系统已停止生成冠军概率/)).toBeInTheDocument();
    expect(screen.getByText('真实球队模型特征尚未补齐')).toBeInTheDocument();
    expect(screen.getByText('没有生成有效冠军概率')).toBeInTheDocument();
    expect(screen.queryByText('冠军概率由赛事路径模拟得到。')).not.toBeInTheDocument();
    expect(screen.getAllByText('当前没有可验证的预测结果，无法确认该模块已进入概率。').length).toBeGreaterThan(0);
    expect(screen.getByText('开发者详情')).toBeInTheDocument();
    expect(screen.queryByText(/这里仅显示经过整理的诊断摘要/)).not.toBeInTheDocument();
    expect(screen.queryByText('internal diagnostic text')).not.toBeInTheDocument();
  });

  it('shows remaining semifinals and opens the match detail drawer', async () => {
    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole('button', { name: '剩余比赛' }));

    expect(await screen.findByText('法国')).toBeInTheDocument();
    expect(screen.getByText('西班牙')).toBeInTheDocument();
    expect(screen.getByText('英格兰')).toBeInTheDocument();
    expect(screen.getAllByText('1-1').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /法国.*西班牙/ }));

    expect(await screen.findByRole('dialog', { name: '单场预测详情' })).toBeInTheDocument();
    expect(screen.getByText('常规时间胜平负')).toBeInTheDocument();
    expect(screen.getByText('融合来源与有效权重')).toBeInTheDocument();
    expect(screen.getByText('让 Agent 解读本场')).toBeInTheDocument();
  });

  it('allows switching the path view to another alive team', async () => {
    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole('button', { name: '冠军路径' }));
    const select = await screen.findByLabelText('选择球队');
    fireEvent.change(select, { target: { value: 'FRA' } });

    expect(screen.getByText('法国 冠军路径')).toBeInTheDocument();
    expect(screen.getByText(/逐轮晋级概率已从模型产物和产品中移除/)).toBeInTheDocument();
    expect(screen.getByText('29.0%')).toBeInTheDocument();
  });

  it('shows a product empty state when no verified artifact is available', async () => {
    apiMock.getTournament.mockRejectedValue(new Error('no published'));
    apiMock.getPredictionCandidate.mockRejectedValue(new Error('no candidate'));
    apiMock.getWorldCupMatches.mockResolvedValue([
      { match_id: 'SF-1', stage: 'SF', status: 'scheduled', home_team_id: 'ARG', away_team_id: 'BRA', kickoff_time: '2026-07-14T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
      { match_id: 'SF-2', stage: 'SF', status: 'scheduled', home_team_id: 'FRA', away_team_id: 'ENG', kickoff_time: '2026-07-15T20:00:00Z', fetched_at: '2026-07-14T00:00:00Z' },
    ]);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    expect(await screen.findByText('当前没有有效冠军预测')).toBeInTheDocument();
    expect(screen.getAllByText(/该阶段暂无通过验证的预测报告/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/暂居冠军概率首位/)).not.toBeInTheDocument();
    expect(screen.queryByText('25.0%')).not.toBeInTheDocument();
    expect(screen.queryByTestId('echarts')).not.toBeInTheDocument();
  });

  it('keeps real remaining fixtures visible without inventing match probabilities', async () => {
    apiMock.getTournament.mockRejectedValue(new Error('no published'));
    apiMock.getPredictionCandidate.mockRejectedValue(new Error('no candidate'));
    apiMock.getWorldCupMatches.mockResolvedValue([
      { match_id: 'SF-1', stage: 'SF', status: 'scheduled', home_team_id: 'ENG', away_team_id: 'ARG', kickoff_time: '2026-07-15T20:00:00Z', fetched_at: '2026-07-15T00:00:00Z' },
      { match_id: 'FINAL', stage: 'Final', status: 'scheduled', home_team_id: 'ESP', away_team_id: 'TBD', kickoff_time: '2026-07-19T20:00:00Z', fetched_at: '2026-07-15T00:00:00Z' },
    ]);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: '剩余比赛' }));

    expect(await screen.findByText('尚无通过验证的比赛概率')).toBeInTheDocument();
    expect(screen.getByText('参赛球队尚未确定')).toBeInTheDocument();
    expect(screen.getAllByText('这里只展示真实赛程，不生成占位概率。')).toHaveLength(2);
    expect(screen.queryByText('25.0%')).not.toBeInTheDocument();
  });

  it('reruns the selected historical stage instead of always using current', async () => {
    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    const select = await screen.findByLabelText('预测起点');
    fireEvent.change(select, { target: { value: 'post_qf' } });
    fireEvent.click(screen.getByRole('button', { name: /重新模拟/ }));

    await waitFor(() => expect(apiMock.runFullPrediction).toHaveBeenCalledWith('post_qf'));
  });

  it('keeps the existing report visible when rerun fails', async () => {
    apiMock.runFullPrediction.mockRejectedValue(new Error('backend failed'));
    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    expect((await screen.findAllByText(/阿根廷 暂居冠军概率首位/)).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /重新模拟/ }));

    expect(await screen.findByText(/当前阶段仍只展示通过正式验证的报告/)).toBeInTheDocument();
    expect(screen.getAllByText(/阿根廷 暂居冠军概率首位/).length).toBeGreaterThan(0);
  });

  it('does not use another stage history snapshot when current has no verified report', async () => {
    const oldRoundOf16 = {
      ...baseArtifact,
      artifact_id: 'published-post-r32-old',
      generated_at: '2026-07-10T00:00:00Z',
      prediction_report: null,
      current_tournament_state: {
        ...baseArtifact.current_tournament_state,
        requested_anchor: 'post_r32',
        anchor_label: '32 强后 / 16 强赛前',
        active_round: 'R16',
      },
    } as TournamentPrediction;
    apiMock.getTournament.mockRejectedValue(new Error('no current report'));
    apiMock.getPredictionCandidate.mockRejectedValue(new Error('no candidate'));
    apiMock.getPredictionSnapshots.mockResolvedValue([{ artifact_id: oldRoundOf16.artifact_id }]);
    apiMock.getPredictionSnapshot.mockResolvedValue(oldRoundOf16);

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);

    expect(await screen.findByText('当前没有有效冠军预测')).toBeInTheDocument();
    await waitFor(() => expect(apiMock.getPredictionSnapshot).toHaveBeenCalled());
    expect(screen.queryByText('34.0%')).not.toBeInTheDocument();
    expect(screen.queryByText(/阿根廷 暂居冠军概率首位/)).not.toBeInTheDocument();
  });

  it('chooses the newest verified snapshot from the exact requested stage', async () => {
    const older = postQfArtifact('post-qf-old', '2026-07-13T20:00:00Z', 'ARG');
    const newer = postQfArtifact('post-qf-new', '2026-07-14T20:00:00Z', 'ESP');
    apiMock.getPredictionSnapshots.mockResolvedValue([
      { artifact_id: newer.artifact_id },
      { artifact_id: older.artifact_id },
    ]);
    apiMock.getPredictionSnapshot.mockImplementation((artifactId: string) =>
      Promise.resolve(artifactId === newer.artifact_id ? newer : older),
    );
    apiMock.getTournament.mockImplementation((anchor: string) =>
      anchor === 'current' ? Promise.resolve(baseArtifact) : Promise.reject(new Error('pointer missing')),
    );

    render(<MemoryRouter initialEntries={['/predictions']}><PredictionsPage /></MemoryRouter>);
    await waitFor(() => expect(apiMock.getPredictionSnapshot).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('预测起点'), { target: { value: 'post_qf' } });

    expect(await screen.findByText(/西班牙 暂居冠军概率首位/)).toBeInTheDocument();
    expect(screen.queryByText(/阿根廷 暂居冠军概率首位/)).not.toBeInTheDocument();
  });
});

function postQfArtifact(artifactId: string, generatedAt: string, leader: 'ARG' | 'ESP') {
  const probabilities = [
    { ...baseArtifact.champion_probabilities[0], team_id: leader, probability: 0.4 },
    { ...baseArtifact.champion_probabilities[1], team_id: 'FRA', probability: 0.25 },
    { ...baseArtifact.champion_probabilities[2], team_id: 'ENG', probability: 0.2 },
    { ...baseArtifact.champion_probabilities[3], team_id: leader === 'ARG' ? 'ESP' : 'ARG', probability: 0.15 },
  ];
  return {
    ...baseArtifact,
    artifact_id: artifactId,
    generated_at: generatedAt,
    rational_champion: leader,
    prediction_report: null,
    champion_probabilities: probabilities,
    current_tournament_state: {
      ...baseArtifact.current_tournament_state,
      requested_anchor: 'post_qf',
      anchor_label: '8 强后 / 4 强赛前',
      alive_teams: probabilities.map((row) => row.team_id),
    },
  } as TournamentPrediction;
}
