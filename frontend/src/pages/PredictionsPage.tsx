import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  FileText,
  Info,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trophy,
  X,
} from 'lucide-react';
import { AgentDrawer } from '../components/AgentDrawer';
import { AppHeader } from '../components/AppHeader';
import { api } from '../lib/api';
import type {
  AgentPageContext,
  ChampionProbability,
  FeatureModuleStatus,
  MatchPrediction,
  PredictionAgentReport,
  PredictionReportFigure,
  PredictionSnapshot,
  PredictionStageAvailability,
  TournamentPrediction,
  TournamentState,
  WorldCupMatch,
  WorldCupSyncStatus,
} from '../lib/types';
import './predictions.css';

type PredictionTab = 'report' | 'matches' | 'path' | 'model';
type StageKey = 'current' | 'pre_tournament' | 'post_group' | 'post_r32' | 'post_r16' | 'post_qf' | 'post_sf';

const TABS: Array<{ key: PredictionTab; label: string }> = [
  { key: 'report', label: '预测报告' },
  { key: 'matches', label: '剩余比赛' },
  { key: 'path', label: '冠军路径' },
  { key: 'model', label: '模型与数据' },
];

const STAGES: Array<{ key: StageKey; label: string; short: string; anchorStage: string; description: string }> = [
  { key: 'current', label: '当前赛况', short: '当前', anchorStage: 'current', description: '基于当前已同步赛程和已锁定赛果，只模拟后续未完成比赛。' },
  { key: 'pre_tournament', label: '赛前', short: '赛前', anchorStage: 'pre_tournament', description: '基于开赛前信息的冠军预测快照。' },
  { key: 'post_group', label: '小组赛后 / 32 强赛前', short: '32 强前', anchorStage: 'post_group', description: '只使用小组赛结束及以前的信息，不引用后续淘汰赛结果。' },
  { key: 'post_r32', label: '32 强后 / 16 强赛前', short: '16 强前', anchorStage: 'post_r32', description: '只使用 32 强结束及以前的信息，不引用后续结果。' },
  { key: 'post_r16', label: '16 强后 / 8 强赛前', short: '8 强前', anchorStage: 'post_r16', description: '只使用 16 强结束及以前的信息，不引用 8 强及之后的信息。' },
  { key: 'post_qf', label: '8 强后 / 4 强赛前', short: '4 强前', anchorStage: 'post_qf', description: '只使用四分之一决赛结束及以前的信息，模拟半决赛之后路径。' },
  { key: 'post_sf', label: '4 强后 / 决赛前', short: '决赛前', anchorStage: 'post_sf', description: '只使用半决赛结束及以前的信息，模拟决赛或季军赛路径。' },
];

const MODULE_ORDER = ['strength', 'goals', 'path', 'market', 'lineup', 'rules', 'discipline', 'environment', 'tactical', 'web_semantic'];

export default function PredictionsPage() {
  const [candidate, setCandidate] = useState<TournamentPrediction | null>(null);
  const [selected, setSelected] = useState<TournamentPrediction | null>(null);
  const [snapshots, setSnapshots] = useState<PredictionSnapshot[]>([]);
  const [stageAvailability, setStageAvailability] = useState<PredictionStageAvailability[]>([]);
  const [history, setHistory] = useState<TournamentPrediction[]>([]);
  const [matches, setMatches] = useState<WorldCupMatch[]>([]);
  const [syncStatus, setSyncStatus] = useState<WorldCupSyncStatus | null>(null);
  const [stage, setStage] = useState<StageKey>('current');
  const [tab, setTab] = useState<PredictionTab>('report');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState('');
  const [productIssue, setProductIssue] = useState('');
  const [debugIssue, setDebugIssue] = useState<unknown>(null);
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentContext, setAgentContext] = useState<AgentPageContext>({ currentPage: 'predictions' });
  const [agentPrompt, setAgentPrompt] = useState('');

  const loadPage = useCallback(async () => {
    const activeStage = STAGES.find((item) => item.key === stage) ?? STAGES[0];
    setLoading(true);
    setProductIssue('');
    setDebugIssue(null);
    const [publishedResult, candidateResult, snapshotResult, matchResult, syncResult, stageResult] = await Promise.allSettled([
      api.getTournament(activeStage.anchorStage),
      api.getPredictionCandidate(activeStage.anchorStage),
      api.getPredictionSnapshots(),
      api.getWorldCupMatches(),
      api.getWorldCupSyncStatus(),
      api.getPredictionStages(),
    ]);
    const nextMatches = matchResult.status === 'fulfilled' ? matchResult.value : [];
    const nextPublished = publishedResult.status === 'fulfilled' ? normalizeArtifact(publishedResult.value, nextMatches) : null;
    const nextCandidate = candidateResult.status === 'fulfilled' ? normalizeArtifact(candidateResult.value, nextMatches) : null;
    setCandidate(nextCandidate);
    const usablePublished = selectArtifactForStage(stage, nextPublished, [], nextMatches);
    setSelected(usablePublished);
    if (snapshotResult.status === 'fulfilled') setSnapshots(snapshotResult.value);
    if (matchResult.status === 'fulfilled') setMatches(nextMatches);
    if (syncResult.status === 'fulfilled') setSyncStatus(syncResult.value);
    const nextAvailability = stageResult.status === 'fulfilled' ? stageResult.value : [];
    if (stageResult.status === 'fulfilled') setStageAvailability(nextAvailability);
    if (!usablePublished) {
      const stageState = nextAvailability.find((item) => item.anchor === activeStage.anchorStage);
      setProductIssue(
        nextCandidate && !(nextCandidate.champion_probabilities ?? []).length
          ? '当前产物未生成有效冠军概率，因此不会展示冠军队伍、概率榜或领先者。'
          : stageState?.message || '该阶段暂无通过验证的预测报告。',
      );
      setDebugIssue(firstRejectedReason(publishedResult, candidateResult));
    }
    setLoading(false);
  }, [stage]);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useEffect(() => {
    if (!snapshots.length) {
      setHistory([]);
      return;
    }
    let active = true;
    void Promise.all(snapshots.map((item) => api.getPredictionSnapshot(item.artifact_id)))
      .then((rows) => { if (active) setHistory(rows.map((item) => normalizeArtifact(item, matches))); })
      .catch(() => { if (active) setHistory([]); });
    return () => { active = false; };
  }, [matches, snapshots]);

  async function handleRun() {
    setRunning(true);
    setNotice('');
    setProductIssue('');
    setDebugIssue(null);
    const previous = selected;
    try {
      const result = await api.runFullPrediction(stageInfo.anchorStage);
      setNotice(result.publish_status === 'published'
        ? '新的预测已经通过数据校验，当前页面已切换到完整预测。'
        : '新的结果未通过正式验证，因此不会作为冠军预测展示。');
      await loadPage();
    } catch (err) {
      setSelected(previous);
      setProductIssue('重新模拟没有生成可发布结果。当前阶段仍只展示通过正式验证的报告。');
      setDebugIssue(debugDetail(err));
    } finally {
      setRunning(false);
    }
  }

  async function handleSync() {
    setSyncing(true);
    setProductIssue('');
    try {
      await api.syncWorldCup();
      await loadPage();
    } catch (err) {
      setProductIssue('赛程数据更新没有完成，当前预测报告仍使用页面上显示的数据截止时间。');
      setDebugIssue(debugDetail(err));
    } finally {
      setSyncing(false);
    }
  }

  const stageInfo = STAGES.find((item) => item.key === stage) ?? STAGES[0];
  const activeStageAvailability = stageAvailability.find((row) => row.anchor === stageInfo.anchorStage);
  const canRunStage = !activeStageAvailability || ['available', 'generatable'].includes(activeStageAvailability.status);
  const reportArtifact = useMemo(() => selectArtifactForStage(stage, selected, history, matches), [history, matches, selected, stage]);
  const report = useMemo(() => buildReport(reportArtifact, matches, stageInfo), [matches, reportArtifact, stageInfo]);

  function openAgent() {
    if (!report.leader) return;
    const context: AgentPageContext = {
      currentPage: 'predictions',
      activeTab: 'report',
      summary: `${stageInfo.label}冠军预测：${teamName(report.leader.team_id)} ${formatPercent(report.leader.probability)}`,
      data: {
        scope: 'tournament',
        stage: stageInfo,
        anchorStage: stageInfo.anchorStage,
        artifactId: reportArtifact?.artifact_id,
        publicationStatus: reportArtifact?.publication_status,
        currentContenders: report.aliveRows.map((row) => row.team_id),
        leader: report.leader,
        competitors: report.competitors.slice(0, 4),
      },
    };
    setAgentContext(context);
    setAgentPrompt('请基于页面已有冠军概率和数据状态，解释这份冠军预测报告的核心依据，不要编造未接入的数据。');
    setAgentOpen(true);
  }

  function openMatchAgent(prediction: MatchPrediction) {
    const context: AgentPageContext = {
      currentPage: 'predictions',
      activeTab: 'matches',
      currentMatchId: prediction.match_id,
      summary: `${teamName(prediction.home_team_id)} vs ${teamName(prediction.away_team_id)} 单场预测`,
      data: {
        artifactId: reportArtifact?.artifact_id,
        anchorStage: stageInfo.anchorStage,
        publicationStatus: reportArtifact?.publication_status,
        homeTeam: prediction.home_team_id,
        awayTeam: prediction.away_team_id,
        prediction,
        stage: stageInfo,
      },
    };
    setAgentContext(context);
    setAgentPrompt('请基于本场胜平负、晋级概率、比分分布、组件权重、缺失字段和模型假设，生成一段专业但不夸大的赛前解读。不要编造赔率、伤停或新闻。');
    setAgentOpen(true);
  }

  return (
    <div className="prediction-shell">
      <div className="prediction-backdrop" />
      <AppHeader syncStatus={syncStatus} syncing={syncing} onSync={handleSync} />
      <main className="prediction-main prediction-report-main">
        <section className="prediction-report-header">
          <div className="prediction-report-title">
            <div className="prediction-title-icon"><Trophy size={24} /></div>
            <div>
              <span className="section-kicker">WORLD CUP CHAMPION FORECAST</span>
              <h2>阶段性冠军预测中心</h2>
              <p>基于指定赛事阶段的冠军概率模拟与预测报告页面。</p>
            </div>
          </div>
          <div className="prediction-header-actions">
            <label htmlFor="stage-select">预测起点</label>
            <select id="stage-select" value={stage} onChange={(event) => setStage(event.target.value as StageKey)}>
              {STAGES.map((item) => {
                const availability = stageAvailability.find((row) => row.anchor === item.anchorStage);
                const suffix = availability?.status === 'available'
                  ? '（已保存）'
                  : availability?.status === 'generatable'
                    ? '（可生成）'
                  : availability?.status === 'not_reached'
                    ? '（尚未到达）'
                  : availability?.status === 'not_captured'
                      ? '（暂不支持）'
                      : '';
                return <option key={item.key} value={item.key}>{item.label}{suffix}</option>;
              })}
            </select>
            <span className={`quality-chip ${report.statusTone}`}>
              {report.statusTone === 'ready' ? <ShieldCheck size={15} /> : <AlertTriangle size={15} />}
              {report.statusLabel}
            </span>
            <button type="button" className="run-button" onClick={handleRun} disabled={running || !canRunStage}>
              <RefreshCw size={17} className={running ? 'animate-spin' : ''} />
              {running ? '同步并模拟中' : '重新模拟'}
            </button>
          </div>
        </section>

        <PredictionStateBanner report={report} productIssue={productIssue} />
        {notice && <div className="prediction-notice"><CheckCircle2 size={17} />{notice}</div>}

        {loading ? <LoadingState /> : (
          <>
            <section className="report-hero-grid">
              <ChampionHeroCard report={report} onAgent={openAgent} />
              <ChampionProbabilityChart report={report} />
            </section>

            <section className="stage-summary-grid">
              <StageFact label="预测起点" value={stageInfo.label} icon={<Clock3 size={18} />} />
              <StageFact label="数据截止时间" value={formatDateTime(report.asOfTime)} icon={<Database size={18} />} />
              <StageFact label="已锁定比赛" value={`${report.completedCount} 场`} icon={<ShieldCheck size={18} />} />
              <StageFact label="剩余模拟比赛" value={`${report.remainingCount} 场`} icon={<RefreshCw size={18} />} />
              <StageFact label="冠军概率覆盖" value={report.artifact ? `${report.aliveRows.length} 支` : '待验证'} icon={<Trophy size={18} />} />
              <StageFact label="模拟次数" value={report.simulationCount ? report.simulationCount.toLocaleString('zh-CN') : '待补充'} icon={<Sparkles size={18} />} />
            </section>

            <nav className="prediction-tabs report-tabs" aria-label="预测中心视图">
              {TABS.map((item) => (
                <button key={item.key} type="button" className={tab === item.key ? 'active' : ''} onClick={() => setTab(item.key)}>{item.label}</button>
              ))}
            </nav>

            <section className="prediction-content report-content">
              {tab === 'report' && <ReportView report={report} history={history} />}
              {tab === 'matches' && <RemainingMatchesView artifact={reportArtifact} schedule={matches} onAgent={openMatchAgent} />}
              {tab === 'path' && <PathView report={report} />}
              {tab === 'model' && <ModelView report={report} candidate={candidate} debugIssue={debugIssue} />}
            </section>
          </>
        )}
      </main>
      <AgentDrawer open={agentOpen} sessionKey={`prediction:${report.leader?.team_id ?? 'page'}`} context={agentContext} initialPrompt={agentPrompt} onClose={() => setAgentOpen(false)} />
    </div>
  );
}

function PredictionStateBanner({ report, productIssue }: { report: PredictionReport; productIssue: string }) {
  const message = productIssue || report.bannerMessage;
  return (
    <div className={`prediction-state-banner ${report.statusTone}`}>
      {report.statusTone === 'ready' ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
      <div>
        <strong>{report.statusLabel}</strong>
        <span>{message}</span>
      </div>
    </div>
  );
}

function ChampionHeroCard({ report, onAgent }: { report: PredictionReport; onAgent: () => void }) {
  const leader = report.leader;
  return (
    <article className="champion-hero-card">
      <div className="hero-card-watermark" aria-hidden="true" />
      <span className="section-kicker">CHAMPION PICK</span>
      <h3>{leader ? `${teamName(leader.team_id)} 暂居冠军概率首位` : '当前没有有效冠军预测'}</h3>
      <div className="hero-probability">{leader ? formatPercent(leader.probability) : '--'}</div>
      <p>
        {leader
          ? `基于${report.stage.label}的可用数据，${teamName(leader.team_id)}位于当前冠军竞争梯队首位。`
          : '当前阶段没有通过正式验证的冠军概率。页面不会使用旧阶段报告、均匀概率或默认球队数据代替。'}
      </p>
      <div className="hero-meta-strip">
        <span>{report.statusLabel}</span>
        <span>{formatDateTime(report.asOfTime)}</span>
        <span>{report.simulationCount ? `${report.simulationCount.toLocaleString('zh-CN')} 次模拟` : '模拟次数待补充'}</span>
      </div>
      <button type="button" className="agent-report-button" onClick={onAgent} disabled={!leader}>
        <Bot size={18} /> 让 Agent 解读报告
      </button>
    </article>
  );
}

function ChampionProbabilityChart({ report }: { report: PredictionReport }) {
  const rows = report.aliveRows;
  const chartType = rows.length <= 8 ? 'pie' : 'bar';
  const dataRows = chartType === 'pie' ? rows : rows.slice(0, 12);
  const other = rows.slice(12).reduce((sum, row) => sum + safeNumber(row.probability), 0);
  const option = chartType === 'pie'
    ? {
        tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
        legend: { bottom: 0, textStyle: { color: '#405148' } },
        series: [{
          type: 'pie',
          radius: ['46%', '72%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          label: { formatter: '{b}\n{d}%', color: '#20372a', fontWeight: 700 },
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
          data: dataRows.map((row) => ({ name: teamName(row.team_id), value: safeNumber(row.probability) })),
        }],
      }
    : {
        grid: { left: 86, right: 46, top: 18, bottom: 30 },
        xAxis: { type: 'value', max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%`, color: '#64746a' }, splitLine: { lineStyle: { color: '#e7ece8' } } },
        yAxis: { type: 'category', data: [...dataRows].reverse().map((row) => teamName(row.team_id)), axisLabel: { color: '#20372a', fontWeight: 700 }, axisTick: { show: false }, axisLine: { show: false } },
        tooltip: { trigger: 'axis', formatter: (params: Array<{ name: string; value: number }>) => `${params[0]?.name}<br/>${formatPercent(params[0]?.value ?? 0)}` },
        series: [{ type: 'bar', data: [...dataRows].reverse().map((row) => safeNumber(row.probability)), barMaxWidth: 24, itemStyle: { color: '#177245', borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', formatter: ({ value }: { value: number }) => formatPercent(value), color: '#20372a', fontWeight: 800 } }],
      };
  return (
    <article className="champion-chart-card">
      <div className="section-heading-row compact">
        <div>
          <span className="section-kicker">PROBABILITY DISTRIBUTION</span>
          <h3>{chartType === 'pie' ? '存活球队夺冠概率' : '冠军概率排行榜'}</h3>
        </div>
      </div>
      {rows.length > 0
        ? <ReactECharts option={option} style={{ height: rows.length <= 8 ? 340 : Math.max(340, dataRows.length * 34) }} notMerge />
        : <div className="soft-empty"><AlertTriangle size={24} /><strong>当前产物未生成有效冠军概率</strong><span>通过正式验证后，冠军概率分布才会在这里展示。</span></div>}
      {chartType === 'bar' && other > 0 && <p className="chart-note">其余球队合计 {formatPercent(other)}，完整概率见下方榜单。</p>}
    </article>
  );
}

function StageFact({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return <div className="stage-fact-card">{icon}<span>{label}</span><strong>{value}</strong></div>;
}

function ReportView({ report, history }: { report: PredictionReport; history: TournamentPrediction[] }) {
  if (!report.leader) {
    return (
      <div className="report-view">
        <section className="report-card timeline-empty">
          <AlertTriangle size={24} />
          <strong>该阶段暂无通过验证的预测报告</strong>
          <span>可以运行生成流程；未通过验证的结果不会显示冠军队伍、排行榜或其他阶段概率。</span>
        </section>
      </div>
    );
  }
  return (
    <div className="report-view">
      <ChampionRankingTable report={report} />
      <ProbabilityTimelineChart history={history} />
      <PredictionReportArticle report={report} />
    </div>
  );
}

function ChampionRankingTable({ report }: { report: PredictionReport }) {
  const leader = report.leader;
  const leaderError = leader ? samplingError(leader.probability, report.simulationCount) : 0;
  const leaderFloor = leader ? leader.probability - leaderError : 0;
  return (
    <section className="report-card">
      <div className="section-heading-row compact">
        <div><span className="section-kicker">ALL ALIVE TEAMS</span><h3>冠军概率排行榜</h3></div>
      </div>
      {!report.aliveRows.length ? <div className="soft-empty"><AlertTriangle size={24} /><strong>暂无有效冠军概率</strong><span>排行榜不会使用前端兜底值生成。</span></div> : <div className="prediction-table-wrap">
        <table className="prediction-table">
          <thead><tr><th>排名</th><th>球队</th><th>夺冠概率</th><th>采样误差</th><th>最可能淘汰者</th><th>决定性对阵</th></tr></thead>
          <tbody>{report.aliveRows.map((row, index) => {
            const error = samplingError(row.probability, report.simulationCount);
            const sameTier = leader ? row.probability + error >= leaderFloor : false;
            return (
              <tr key={row.team_id}>
                <td>{index + 1}</td>
                <td><strong>{teamName(row.team_id)}</strong>{sameTier && <span className="cohort-tag">同一竞争梯队</span>}</td>
                <td><b>{formatPercent(row.probability)}</b></td>
                <td>{report.simulationCount ? `±${formatPercent(error)}` : '未标注'}</td>
                <td>{teamName(row.eliminator_stats?.[0]?.opponent_team_id || row.most_common_eliminator) || '暂无稳定项'}</td>
                <td>{matchupLabel(row)}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>}
    </section>
  );
}

function ProbabilityTimelineChart({ history }: { history: TournamentPrediction[] }) {
  const timeline = [...history]
    .filter((item) => isUsablePublishedArtifact(item, item.current_tournament_state?.requested_anchor ?? ''))
    .sort((left, right) => artifactTime(left) - artifactTime(right));
  const teams = Array.from(new Set(timeline.flatMap((item) => liveChampionRows(item).slice(0, 5).map((row) => row.team_id)))).slice(0, 6);
  if (timeline.length < 2 || teams.length === 0) {
    return (
      <section className="report-card timeline-empty">
        <Info size={24} />
        <strong>概率演化从正式快照开始积累</strong>
        <span>至少产生两份正式发布快照后，这里会展示冠军概率随阶段变化的折线图。</span>
      </section>
    );
  }
  const option = {
    color: ['#177245', '#b68b16', '#2455a4', '#a33c48', '#5d4b8a', '#347c82'],
    grid: { left: 45, right: 18, top: 36, bottom: 52 },
    tooltip: { trigger: 'axis' },
    legend: { data: teams.map(teamName), top: 0, textStyle: { color: '#405148' } },
    xAxis: { type: 'category', data: timeline.map((item) => item.current_tournament_state?.anchor_label ?? formatDateTime(item.generated_at)), axisLabel: { color: '#64746a', rotate: 18 } },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%`, color: '#64746a' }, splitLine: { lineStyle: { color: '#e7ece8' } } },
    series: teams.map((teamId) => ({ name: teamName(teamId), type: 'line', smooth: true, symbolSize: 7, data: timeline.map((item) => liveChampionRows(item).find((row) => row.team_id === teamId)?.probability ?? 0) })),
  };
  return <section className="report-card"><ReactECharts option={option} style={{ height: 320 }} /></section>;
}

function PredictionReportArticle({ report }: { report: PredictionReport }) {
  const agentReport = report.agentReport;
  if (agentReport) {
    const references = agentReport.references ?? [];
    const title = agentReport.title || agentReport.headline || '世界杯冠军概率预测报告';
    const abstract = agentReport.abstract || agentReport.summary || agentReport.headline;
    return (
      <article className="prediction-article agent-generated-report">
        <section>
          <h3><FileText size={19} />{title}</h3>
          <p>{abstract}</p>
        </section>
        {agentReport.sections.map((section) => (
          <section key={section.title}>
            <h3>{section.title}</h3>
            <p>{section.body}</p>
            {section.bullets.length > 0 && (
              <ul>
                {section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}
              </ul>
            )}
            {(section.figure_refs ?? []).length > 0 && <ReportFigures refs={section.figure_refs ?? []} figures={agentReport.figures ?? []} />}
            {(section.citations ?? []).length > 0 && <CitationRefs refs={section.citations ?? []} references={references} />}
          </section>
        ))}
        {agentReport.data_disclosure && (
          <section>
            <h3>数据披露</h3>
            <p>{agentReport.data_disclosure}</p>
          </section>
        )}
        {references.length > 0 && (
          <section>
            <h3>参考来源</h3>
            <ul>
              {references.map((item) => (
                <li key={item.reference_id}>
                  {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.label || item.source_name}</a> : <span>{item.label || item.source_name}</span>}
                  {item.note ? `：${item.note}` : ''}
                </li>
              ))}
            </ul>
          </section>
        )}
        {agentReport.caveats.length > 0 && (
          <section>
            <h3>边界说明</h3>
            <ul>
              {agentReport.caveats.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>
        )}
      </article>
    );
  }
  return (
    <article className="prediction-article report-unavailable">
      <section>
        <h3><FileText size={19} />本次预测暂缺正式解读</h3>
        <p>冠军概率已经通过校验，但配套解读报告未生成或未通过公开内容检查。请重新生成预测后再查看，页面不会自行补写理由或引用旧报告。</p>
      </section>
    </article>
  );
}

function ReportFigures({ refs, figures }: { refs: string[]; figures: PredictionReportFigure[] }) {
  const byId = new Map(figures.map((figure) => [figure.figure_id, figure]));
  const selected = refs.map((ref) => byId.get(ref)).filter(Boolean) as PredictionReportFigure[];
  if (!selected.length) return null;
  return <div className="report-figures">{selected.map((figure) => <ReportFigure key={figure.figure_id} figure={figure} />)}</div>;
}

function ReportFigure({ figure }: { figure: PredictionReportFigure }) {
  const data = figure.data ?? {};
  if (figure.kind === 'champion_probability') {
    const teams = arrayRecords(data.teams);
    const option = {
      grid: { left: 72, right: 32, top: 12, bottom: 28 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value: number) => formatPercent(value) },
      xAxis: { type: 'value', max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` }, splitLine: { lineStyle: { color: '#e7ece8' } } },
      yAxis: { type: 'category', inverse: true, data: teams.map((item) => String(item.team_name || teamName(String(item.team_id || '')))) },
      series: [{ type: 'bar', data: teams.map((item) => safeNumber(item.probability)), itemStyle: { color: '#177245', borderRadius: [0, 5, 5, 0] }, label: { show: true, position: 'right', formatter: ({ value }: { value: number }) => formatPercent(value) } }],
    };
    return <FigureCard figure={figure}><ReactECharts option={option} style={{ height: Math.max(220, teams.length * 42) }} /></FigureCard>;
  }
  if (figure.kind === 'champion_scenarios') {
    const rows = arrayRecords(data.scenarios);
    const labels = rows.map((item) => teamName(String(item.opponent_team_id || '')));
    const option = {
      color: ['#d7a719', '#177245'],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (value: number) => formatPercent(value),
      },
      legend: {
        top: 0,
        left: 8,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: '#405148', fontSize: 12 },
        data: ['成为对手的概率', '该情景下夺冠概率'],
      },
      grid: { left: 74, right: 34, top: 58, bottom: 22, containLabel: true },
      xAxis: {
        type: 'value',
        max: 1,
        axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%`, color: '#64746a' },
        splitLine: { lineStyle: { color: '#e1e8e3' } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: labels,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#d8e1db' } },
        axisLabel: { color: '#20372a', fontWeight: 700 },
      },
      series: [
        {
          name: '成为对手的概率',
          type: 'bar',
          barMaxWidth: 18,
          data: rows.map((item) => safeNumber(item.encounter_probability)),
          label: { show: true, position: 'right', formatter: ({ value }: { value: number }) => formatPercent(value), color: '#5a4a13', fontWeight: 700 },
        },
        {
          name: '该情景下夺冠概率',
          type: 'bar',
          barMaxWidth: 18,
          data: rows.map((item) => safeNumber(item.conditional_win_probability)),
          label: { show: true, position: 'right', formatter: ({ value }: { value: number }) => formatPercent(value), color: '#123f27', fontWeight: 700 },
        },
      ],
    };
    return rows.length ? <FigureCard figure={figure}><ReactECharts option={option} style={{ height: Math.max(260, rows.length * 72) }} notMerge /></FigureCard> : null;
  }
  if (figure.kind === 'match_model_comparison') {
    const match = arrayRecords(data.matches)[0];
    if (!match) return null;
    const components = arrayRecords(match.components);
    const final = recordValue(match.final);
    const categories = [...components.map((item) => componentName(String(item.name || ''))), '最终融合'];
    const option = {
      color: ['#2455a4', '#8b968f', '#b3424a'],
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => formatPercent(value) },
      legend: { data: [teamName(String(match.home_team_id || '')), '平局', teamName(String(match.away_team_id || ''))] },
      grid: { left: 62, right: 18, top: 48, bottom: 56 },
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: 16 } },
      yAxis: { type: 'value', max: 0.7, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` } },
      series: [
        { name: teamName(String(match.home_team_id || '')), type: 'bar', data: [...components.map((item) => safeNumber(item.home_win_prob)), safeNumber(final.home)] },
        { name: '平局', type: 'bar', data: [...components.map((item) => safeNumber(item.draw_prob)), safeNumber(final.draw)] },
        { name: teamName(String(match.away_team_id || '')), type: 'bar', data: [...components.map((item) => safeNumber(item.away_win_prob)), safeNumber(final.away)] },
      ],
    };
    return <FigureCard figure={figure}><ReactECharts option={option} style={{ height: 330 }} /></FigureCard>;
  }
  if (figure.kind === 'team_features') {
    const teams = arrayRecords(data.teams).slice(0, 6);
    const indicators = [
      ['综合实力', 'team_strength'], ['近期状态', 'recent_form'], ['进攻', 'attack'],
      ['防守', 'defense'], ['经验', 'world_cup_experience'], ['阵容可用度', 'squad_health'],
    ];
    const option = {
      tooltip: {},
      legend: { data: teams.map((item) => teamName(String(item.team_id || ''))), bottom: 0 },
      radar: { indicator: indicators.map(([name]) => ({ name, max: 1 })), radius: '60%' },
      series: [{ type: 'radar', data: teams.map((item) => ({ name: teamName(String(item.team_id || '')), value: indicators.map(([, key]) => safeNumber(item[key])) })) }],
    };
    return teams.length ? <FigureCard figure={figure}><ReactECharts option={option} style={{ height: 350 }} /></FigureCard> : null;
  }
  if (figure.kind === 'evidence_cards') {
    const items = arrayRecords(data.items);
    return <FigureCard figure={figure}><div className="grounded-evidence-grid">{items.map((item, index) => {
      const usage = String(item.model_usage || 'context_only');
      return <article key={`${String(item.evidence_id || index)}-${index}`}>
        <div><span className={`usage-tag ${usage}`}>{evidenceUsageLabel(usage)}</span><span>{String(item.source_name || '外部来源')}</span></div>
        <h5>{String(item.claim || '赛前线索')}</h5>
        {item.detail ? <p>{String(item.detail)}</p> : null}
        {item.impact_summary ? <strong>{String(item.impact_summary)}</strong> : null}
        {item.url ? <a href={String(item.url)} target="_blank" rel="noreferrer">查看来源</a> : null}
      </article>;
    })}</div></FigureCard>;
  }
  return null;
}

function FigureCard({ figure, children }: { figure: PredictionReportFigure; children: ReactNode }) {
  return <div className="report-figure-card"><header><h4>{figure.title}</h4><p>{figure.description}</p></header>{children}</div>;
}

function arrayRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object') : [];
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function evidenceUsageLabel(value: string) {
  return ({ applied: '已修正概率', model_input: '已进入模型', context_only: '背景信息' } as Record<string, string>)[value] ?? '背景信息';
}

function CitationRefs({ refs, references }: { refs: string[]; references: NonNullable<PredictionAgentReport['references']> }) {
  const byId = new Map(references.map((item) => [item.reference_id, item]));
  const labels = refs.map((ref) => byId.get(ref)).filter(Boolean) as NonNullable<PredictionAgentReport['references']>;
  if (!labels.length) return null;
  return <div className="citation-strip">{labels.map((item) => item.url ? <a key={item.reference_id} href={item.url} target="_blank" rel="noreferrer">{item.label}</a> : <span key={item.reference_id}>{item.label}</span>)}</div>;
}

function RemainingMatchesView({ artifact, schedule, onAgent }: { artifact: TournamentPrediction | null; schedule: WorldCupMatch[]; onAgent: (prediction: MatchPrediction) => void }) {
  const scheduleById = useMemo(() => new Map(schedule.map((row) => [row.match_id, row])), [schedule]);
  const predictionById = useMemo(() => new Map((artifact?.match_predictions ?? []).map((row) => [row.match_id, row])), [artifact]);
  const allRows = useMemo(() => {
    const rows: Array<{ fixture: WorldCupMatch | undefined; prediction: MatchPrediction | null }> = schedule.map((fixture) => ({ fixture, prediction: predictionById.get(fixture.match_id) ?? null }));
    for (const prediction of artifact?.match_predictions ?? []) {
      if (!scheduleById.has(prediction.match_id)) rows.push({ fixture: undefined, prediction });
    }
    return rows.sort((a, b) => String(a.fixture?.kickoff_time ?? '').localeCompare(String(b.fixture?.kickoff_time ?? '')));
  }, [artifact, predictionById, schedule, scheduleById]);
  const stages = useMemo(() => Array.from(new Set(allRows.map((row) => row.fixture?.stage || 'SF'))), [allRows]);
  const teams = useMemo(() => Array.from(new Set(allRows.flatMap((row) => [row.prediction?.home_team_id ?? row.fixture?.home_team_id, row.prediction?.away_team_id ?? row.fixture?.away_team_id]).filter(isDisplayTeam))).sort(), [allRows]);
  const grades = useMemo(() => Array.from(new Set(allRows.map((row) => row.prediction?.data_grade).filter(Boolean) as string[])).sort(), [allRows]);
  const [stageFilter, setStageFilter] = useState('all');
  const [teamFilter, setTeamFilter] = useState('all');
  const [gradeFilter, setGradeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<'remaining' | 'locked' | 'all'>('remaining');
  const [selectedMatch, setSelectedMatch] = useState<MatchPrediction | null>(null);
  const rows = allRows.filter((row) => {
    const fixture = row.fixture;
    const prediction = row.prediction;
    const locked = Boolean(prediction?.is_locked_result) || isCompleteStatus(fixture?.status);
    if (statusFilter === 'remaining' && locked) return false;
    if (statusFilter === 'locked' && !locked) return false;
    if (stageFilter !== 'all' && (fixture?.stage || 'SF') !== stageFilter) return false;
    const home = prediction?.home_team_id ?? fixture?.home_team_id;
    const away = prediction?.away_team_id ?? fixture?.away_team_id;
    if (teamFilter !== 'all' && home !== teamFilter && away !== teamFilter) return false;
    if (gradeFilter !== 'all' && prediction?.data_grade !== gradeFilter) return false;
    return true;
  });
  return (
    <div className="matches-view">
      <div className="section-heading-row compact"><div><span className="section-kicker">REMAINING FIXTURES</span><h3>剩余比赛概率</h3></div><span className="result-count">{rows.length} 场</span></div>
      <div className="match-filters">
        <select aria-label="比赛状态" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
          <option value="remaining">未完成比赛</option>
          <option value="locked">真实结果已锁定</option>
          <option value="all">全部比赛</option>
        </select>
        <select aria-label="阶段筛选" value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
          <option value="all">全部阶段</option>
          {stages.map((stage) => <option key={stage} value={stage}>{stageName(stage)}</option>)}
        </select>
        <select aria-label="球队筛选" value={teamFilter} onChange={(event) => setTeamFilter(event.target.value)}>
          <option value="all">全部球队</option>
          {teams.map((team) => <option key={team} value={team}>{teamName(team)}</option>)}
        </select>
        <select aria-label="数据等级筛选" value={gradeFilter} onChange={(event) => setGradeFilter(event.target.value)}>
          <option value="all">全部等级</option>
          {grades.map((grade) => <option key={grade} value={grade}>数据等级 {grade}</option>)}
        </select>
      </div>
      {!rows.length ? <div className="soft-empty"><CheckCircle2 size={24} /><strong>当前没有符合筛选条件的比赛</strong><span>赛程与预测概率会分别标明，不会把待定对阵当成已确认球队。</span></div> : (
        <div className="match-list">{rows.map((row) => {
          const fixture = row.fixture;
          const prediction = row.prediction;
          const matchId = prediction?.match_id ?? fixture?.match_id ?? '';
          const home = prediction?.home_team_id ?? fixture?.home_team_id;
          const away = prediction?.away_team_id ?? fixture?.away_team_id;
          const locked = Boolean(prediction?.is_locked_result) || isCompleteStatus(fixture?.status);
          if (!prediction) {
            const matchupReady = isDisplayTeam(home) && isDisplayTeam(away);
            return (
              <div key={matchId} className="match-row report-match-row schedule-only-row">
                <div className="match-identity"><span>{stageName(fixture?.stage)}</span><small>{locked ? '真实结果已锁定' : formatDateTime(fixture?.kickoff_time)}</small><strong>{isDisplayTeam(home) ? teamName(home) : '对阵待定'} <em>vs</em> {isDisplayTeam(away) ? teamName(away) : '对阵待定'}</strong></div>
                <div className="schedule-probability-pending"><strong>{matchupReady ? '尚无通过验证的比赛概率' : '参赛球队尚未确定'}</strong><span>这里只展示真实赛程，不生成占位概率。</span></div>
                <div className="match-model-output"><span>预测比分</span><strong>--</strong><small>等待有效预测</small></div>
                <div className="match-confidence"><strong>--</strong><small>模型置信度</small></div>
              </div>
            );
          }
          return (
            <button key={matchId} type="button" className="match-row report-match-row" onClick={() => setSelectedMatch(prediction)}>
              <div className="match-identity"><span>{stageName(fixture?.stage)}</span><small>{locked ? '真实结果已锁定' : formatDateTime(fixture?.kickoff_time)}</small><strong>{teamName(prediction.home_team_id)} <em>vs</em> {teamName(prediction.away_team_id)}</strong></div>
              <ProbabilityBar prediction={prediction} />
              <div className="match-model-output"><span>最可能比分</span><strong>{prediction.predicted_score || '-'}</strong><small>xG {safeNumber(prediction.expected_home_goals).toFixed(2)} - {safeNumber(prediction.expected_away_goals).toFixed(2)}</small></div>
              <div className="match-confidence"><span className={`grade grade-${prediction.data_grade ?? 'E'}`}>{prediction.data_grade ?? 'E'}</span><strong>{formatPercent(prediction.confidence)}</strong><small>模型置信度</small></div>
              <ChevronRight size={20} />
            </button>
          );
        })}</div>
      )}
      {selectedMatch && <MatchPredictionDrawer prediction={selectedMatch} fixture={scheduleById.get(selectedMatch.match_id)} onClose={() => setSelectedMatch(null)} onAgent={onAgent} />}
    </div>
  );
}

function MatchPredictionDrawer({ prediction, fixture, onClose, onAgent }: { prediction: MatchPrediction; fixture?: WorldCupMatch; onClose: () => void; onAgent: (prediction: MatchPrediction) => void }) {
  const scores = (prediction.score_distribution ?? []).slice(0, 8);
  const components = prediction.probability_components ?? [];
  const locked = prediction.is_locked_result || isCompleteStatus(fixture?.status);
  return (
    <div className="match-drawer-backdrop" role="dialog" aria-modal="true" aria-label="单场预测详情">
      <aside className="prediction-match-drawer">
        <header>
          <div>
            <span>{locked ? '真实结果已锁定' : '模拟对阵'}</span>
            <h3>{teamName(prediction.home_team_id)} vs {teamName(prediction.away_team_id)}</h3>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭详情"><X size={18} /></button>
        </header>
        <div className="drawer-scroll">
          <section>
            <h4>常规时间胜平负</h4>
            <ProbabilityBar prediction={prediction} />
            <div className="advance-row"><span>{teamName(prediction.home_team_id)} 最终晋级</span><b>{formatPercent(prediction.home_advancement_prob)}</b></div>
            <div className="advance-row"><span>{teamName(prediction.away_team_id)} 最终晋级</span><b>{formatPercent(prediction.away_advancement_prob)}</b></div>
          </section>
          <section>
            <h4>高概率比分分布</h4>
            {scores.length ? <div className="score-grid">{scores.map((score) => <div key={`${score.home_goals}-${score.away_goals}`}><strong>{score.home_goals}-{score.away_goals}</strong><span>{formatPercent(score.probability)}</span></div>)}</div> : <p>当前报告未提供高概率比分分布。</p>}
          </section>
          <section>
            <h4>融合来源与有效权重</h4>
            <div className="component-list">{components.map((component) => <div key={component.name}><strong>{componentName(component.name)}</strong><span>有效权重 {formatPercent(component.effective_weight)} · 置信度 {formatPercent(component.confidence)}</span><small>主胜 {formatPercent(component.home_win_prob)} / 平局 {formatPercent(component.draw_prob)} / 客胜 {formatPercent(component.away_win_prob)}</small></div>)}</div>
          </section>
          <section>
            <h4>临场修正与数据边界</h4>
            {prediction.applied_adjustments?.length ? <ul>{prediction.applied_adjustments.map((item) => <li key={item.factor}>{adjustmentName(item.factor)}：{item.rationale || '已计入概率修正。'}</li>)}</ul> : <p className="inline-note">本场没有阵容、停赛、体能、环境或战术修正进入本次概率。</p>}
            {prediction.missing_fields?.length ? <ul>{prediction.missing_fields.map((item) => <li key={item}>{humanMissing(item)}</li>)}</ul> : <p>本场未报告阻断性缺失字段。</p>}
          </section>
          <section>
            <h4>证据与模型假设</h4>
            <div className="evidence-list">{modelAssumptions(prediction).map((item) => <div key={item.title}><strong>{item.title}</strong><span>{item.text}</span></div>)}</div>
          </section>
        </div>
        <footer><button type="button" onClick={() => onAgent(prediction)}><Bot size={17} />让 Agent 解读本场</button></footer>
      </aside>
    </div>
  );
}

function PathView({ report }: { report: PredictionReport }) {
  const [selectedTeam, setSelectedTeam] = useState(report.leader?.team_id ?? '');
  const selectedRow = report.aliveRows.find((row) => row.team_id === selectedTeam) ?? report.leader;
  const row = selectedRow;
  useEffect(() => {
    if (!selectedTeam && report.leader?.team_id) setSelectedTeam(report.leader.team_id);
    if (selectedTeam && !report.aliveRows.some((item) => item.team_id === selectedTeam)) setSelectedTeam(report.leader?.team_id ?? '');
  }, [report.aliveRows, report.leader, selectedTeam]);
  if (!row) {
    return <div className="soft-empty"><AlertTriangle size={24} /><strong>暂无可展示的冠军路径</strong><span>当前阶段没有通过验证的冠军概率，因此不会生成球队路径。</span></div>;
  }
  return (
    <div className="path-view">
      <div className="section-heading-row compact">
        <div><span className="section-kicker">CHAMPION PATH</span><h3>{row ? `${teamName(row.team_id)} 冠军路径` : '冠军路径'}</h3></div>
        <select aria-label="选择球队" value={row?.team_id ?? ''} onChange={(event) => setSelectedTeam(event.target.value)}>
          {report.aliveRows.map((item) => <option key={item.team_id} value={item.team_id}>{teamName(item.team_id)}</option>)}
        </select>
      </div>
      <div className="champion-path-probability"><span>夺冠概率</span><strong>{formatPercent(row.probability)}</strong><p>这里只保留冠军概率；逐轮晋级概率已从模型产物和产品中移除。</p></div>
      <div className="path-observations">
        <div><span>常见淘汰者</span><strong>{teamName(row?.eliminator_stats?.[0]?.opponent_team_id || row?.most_common_eliminator) || '暂无稳定项'}</strong></div>
        <div><span>潜在关键战</span><strong>{row ? matchupLabel(row) : '暂无'}</strong></div>
      </div>
      <div className="path-note"><Info size={18} />当前路径来自条件 Monte Carlo 统计，不把固定 seed 的单次路径当作确定赛程。</div>
    </div>
  );
}

function ModelView({ report, candidate, debugIssue }: { report: PredictionReport; candidate: TournamentPrediction | null; debugIssue: unknown }) {
  const grades = (report.artifact?.match_predictions ?? []).reduce<Record<string, number>>((result, row) => {
    const grade = row.data_grade ?? 'E';
    return { ...result, [grade]: (result[grade] ?? 0) + 1 };
  }, {});
  return (
    <div className="model-view">
      <div className="model-facts">
        <Meta label="生成时间" value={formatDateTime(report.generatedAt)} />
        <Meta label="输入快照" value={formatDateTime(report.asOfTime)} />
        <Meta label="模拟次数" value={report.simulationCount ? report.simulationCount.toLocaleString('zh-CN') : '未标注'} />
        <Meta label="预测状态" value={report.statusLabel} />
      </div>
      <section className="model-section">
        <h4>数据模块接入状态</h4>
        {legacyPredictionPayload(report.artifact) && (
          <div className="model-warning">
            <AlertTriangle size={18} />
            <div>
              <strong>当前展示的是旧预测产物或旧报告缓存</strong>
              <p>页面已用现有概率数据重建用户报告，但赔率、联网伤停、黄牌、天气和新闻语义是否真正进入概率，需要重新生成预测后以数据源状态为准。旧产物不会被当成端到端验收通过。</p>
            </div>
          </div>
        )}
        <FeatureModuleStatusPanel modules={report.modules} />
        <SourceStatusPanel artifact={report.artifact} />
      </section>
      <section className="model-section">
        <h4>数据等级与缺失</h4>
        <div className="grade-summary">{['A', 'B', 'C', 'D', 'E'].map((grade) => <div key={grade}><span className={`grade grade-${grade}`}>{grade}</span><strong>{grades[grade] ?? 0}</strong><small>场比赛</small></div>)}</div>
        <div className="quality-report"><strong>{report.statusLabel}</strong><p>{report.qualityMessage}</p>{report.missingItems.length ? <ul>{report.missingItems.slice(0, 8).map((item) => <li key={item}>{humanMissing(item)}</li>)}</ul> : <span>当前未报告阻断性缺失。</span>}</div>
      </section>
      {candidate && candidate.artifact_id !== report.artifact?.artifact_id && <section className="model-section"><h4>最近一次生成结果</h4><div className="candidate-summary"><AlertTriangle size={19} /><div><strong>未通过正式验证</strong><p>{publicQualityMessage(candidate)}</p>{candidate.data_quality_report?.missing?.length ? <ul>{candidate.data_quality_report.missing.slice(0, 8).map((item) => <li key={item}>{humanMissing(item)}</li>)}</ul> : null}</div></div></section>}
      <DeveloperDebugPanel artifact={report.artifact} debugIssue={debugIssue} />
    </div>
  );
}

function FeatureModuleStatusPanel({ modules }: { modules: Record<string, FeatureModuleStatus> }) {
  return (
    <div className="module-grid">
      {MODULE_ORDER.map((name) => {
        const module = modules[name] ?? fallbackModule(name);
        return (
          <div key={name} className={module.status === 'not_connected' ? 'module-muted' : ''}>
            <span className={`module-status ${module.status}`}>{moduleStatusLabel(module.status)}</span>
            <strong>{componentName(name)}</strong>
            <p>{module.message || (module.status === 'not_connected' ? '本次预测未使用该数据。' : '已参与本次概率计算。')}</p>
            <small>覆盖 {formatPercent(module.coverage ?? 0)}</small>
          </div>
        );
      })}
    </div>
  );
}

function SourceStatusPanel({ artifact }: { artifact: TournamentPrediction | null }) {
  const sources = artifact?.data_sources?.length ? artifact.data_sources : artifact?.data_quality_report?.source_statuses ?? [];
  return (
    <div className="source-status-panel">
      <h5>外部证据来源状态</h5>
      {!sources.length ? (
        <p>当前产物没有记录 API-Football 或联网搜索的来源状态。通常意味着这份预测生成于实时证据接入前，或尚未重新运行新版预测链路。</p>
      ) : (
        <div className="source-status-list">
          {sources.slice(0, 20).map((source) => (
            <div key={`${source.source_key}-${source.status}`}>
              <strong>{dataSourceLabel(source.source_key)}</strong>
              <span>{dataSourceStatusText(source.status)}</span>
              <p>{publicSourceMessage(source.status, source.message)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DeveloperDebugPanel({ artifact, debugIssue }: { artifact: TournamentPrediction | null; debugIssue: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="developer-debug-panel" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>开发者详情</summary>
      {open && (
        <div className="quality-report">
          <p>这里仅显示经过整理的诊断摘要，不直接暴露接口响应或原始错误内容。</p>
          <ul>
            <li>读取状态：{artifact ? '已读取预测版本' : '未读取到正式预测版本'}</li>
            <li>验证状态：{artifact?.data_quality_report?.status === 'ready' ? '已通过' : '未通过'}</li>
            <li>问题摘要：{publicDebugMessage(debugIssue)}</li>
          </ul>
        </div>
      )}
    </details>
  );
}

function ProbabilityBar({ prediction }: { prediction: MatchPrediction }) {
  return <div className="probability-block"><div className="probability-labels"><span>{formatPercent(prediction.home_win_prob)}</span><span>平 {formatPercent(prediction.draw_prob)}</span><span>{formatPercent(prediction.away_win_prob)}</span></div><div className="probability-bar"><i style={{ width: `${safeNumber(prediction.home_win_prob) * 100}%` }} /><i style={{ width: `${safeNumber(prediction.draw_prob) * 100}%` }} /><i style={{ width: `${safeNumber(prediction.away_win_prob) * 100}%` }} /></div></div>;
}

function Meta({ label, value }: { label: string; value: string }) { return <div className="meta-item"><span>{label}</span><strong>{value || '--'}</strong></div>; }
function LoadingState() { return <div className="content-empty"><RefreshCw className="animate-spin" size={25} /><strong>正在读取预测报告</strong></div>; }

interface PredictionReport {
  artifact: TournamentPrediction | null;
  stage: (typeof STAGES)[number];
  leader: ChampionProbability | null;
  competitors: ChampionProbability[];
  aliveRows: ChampionProbability[];
  statusLabel: string;
  statusTone: 'ready' | 'trial';
  bannerMessage: string;
  qualityMessage: string;
  missingItems: string[];
  modules: Record<string, FeatureModuleStatus>;
  completedCount: number;
  remainingCount: number;
  simulationCount: number;
  asOfTime: string | null;
  generatedAt: string | null;
  agentReport: PredictionAgentReport | null;
}

function buildReport(artifact: TournamentPrediction | null, schedule: WorldCupMatch[], stage: (typeof STAGES)[number]): PredictionReport {
  const state = artifact?.current_tournament_state ?? deriveStateFromSchedule(schedule, artifact);
  const rows = artifact ? liveChampionRows(artifact) : [];
  const leader = rows[0] ?? null;
  const missing = artifact?.data_quality_report?.missing ?? [];
  const statusTone = artifact && isUsablePublishedArtifact(artifact, stage.anchorStage) ? 'ready' : 'trial';
  const statusLabel = statusTone === 'ready'
    ? '完整预测'
    : '暂无有效预测';
  return {
    artifact,
    stage,
    leader,
    competitors: rows,
    aliveRows: rows,
    statusLabel,
    statusTone,
    bannerMessage: statusTone === 'ready'
      ? '当前展示的是已通过数据校验的完整预测。'
      : '该阶段暂无通过验证的预测报告。页面不会使用其他阶段或未经验证的结果代替。',
    qualityMessage: artifact?.data_quality_report?.message || '当前阶段没有可作为正式预测展示的结果。',
    missingItems: missing,
    modules: normalizeModules(artifact),
    completedCount: state.completed_match_ids.length,
    remainingCount: state.remaining_match_ids.length,
    simulationCount: artifact?.simulation_count || rows[0]?.simulation_count || 0,
    asOfTime: artifact?.input_data_as_of || state.as_of_time || artifact?.generated_at || null,
    generatedAt: artifact?.generated_at ?? null,
    agentReport: leader ? usableAgentReport(artifact?.prediction_report) : null,
  };
}

function normalizeArtifact(artifact: TournamentPrediction, schedule: WorldCupMatch[]): TournamentPrediction {
  return {
    ...artifact,
    artifact_id: artifact.artifact_id || '',
    publication_status: artifact.publication_status || 'legacy',
    probability_profile: artifact.probability_profile || artifact.mode || 'unknown',
    simulation_count: artifact.simulation_count || artifact.champion_probabilities?.[0]?.simulation_count || 0,
    current_tournament_state: artifact.current_tournament_state ?? deriveStateFromSchedule(schedule, artifact),
    feature_modules: normalizeModules(artifact),
    data_quality_report: artifact.data_quality_report ?? {
      status: 'invalid',
      strict: true,
      missing: [],
      conflicts: [],
      invalid_records: [],
      source_statuses: [],
      message: '该预测缺少完整质量记录，不能作为正式报告展示。',
    },
  };
}

function selectArtifactForStage(stage: StageKey, selected: TournamentPrediction | null, history: TournamentPrediction[], schedule: WorldCupMatch[]) {
  const target = STAGES.find((item) => item.key === stage);
  const anchor = target?.anchorStage ?? 'current';
  return [selected, ...history]
    .filter((item): item is TournamentPrediction => Boolean(item))
    .filter((item) => isUsablePublishedArtifact(item, anchor))
    .filter((item) => anchor !== 'current' || currentArtifactMatchesSchedule(item, schedule))
    .sort((left, right) => artifactTime(right) - artifactTime(left))[0] ?? null;
}

function liveChampionRows(artifact: TournamentPrediction | null) {
  return (artifact?.champion_probabilities ?? [])
    .filter((row) => (row.is_alive ?? true) && isDisplayTeam(row.team_id) && safeNumber(row.probability) > 0)
    .sort((a, b) => safeNumber(b.probability) - safeNumber(a.probability));
}

function isUsablePublishedArtifact(artifact: TournamentPrediction, expectedAnchor: string) {
  const state = artifact.current_tournament_state;
  const rows = liveChampionRows(artifact);
  const probabilitySum = (artifact.champion_probabilities ?? []).reduce((sum, row) => sum + safeNumber(row.probability), 0);
  const alive = new Set(state?.alive_teams ?? []);
  return artifact.publication_status === 'published'
    && artifact.data_verified === true
    && artifact.data_quality_report?.status === 'ready'
    && state?.validation_status === 'ready'
    && state.requested_anchor === expectedAnchor
    && artifact.simulation_count >= 10_000
    && rows.length > 0
    && Math.abs(probabilitySum - 1) <= 1e-6
    && rows.every((row) => alive.has(row.team_id) && row.simulation_count >= 10_000);
}

function currentArtifactMatchesSchedule(artifact: TournamentPrediction, schedule: WorldCupMatch[]) {
  const state = artifact.current_tournament_state;
  if (!state || !schedule.length) return false;
  const championshipRounds = new Set(['R32', 'R16', 'QF', 'SF', 'Final']);
  const completedIds = schedule.filter((row) => isCompleteStatus(row.status)).map((row) => row.match_id);
  const remainingIds = schedule
    .filter((row) => championshipRounds.has(String(row.stage)) && !isCompleteStatus(row.status))
    .map((row) => row.match_id);
  const activeRound = ['group', 'R32', 'R16', 'QF', 'SF', 'Final'].find((round) =>
    schedule.some((row) => row.stage === round && !isCompleteStatus(row.status)),
  ) ?? 'complete';
  return state.active_round === activeRound
    && sameStringSet(state.completed_match_ids, completedIds)
    && sameStringSet(state.remaining_match_ids, remainingIds);
}

function sameStringSet(left: string[], right: string[]) {
  return left.length === right.length && left.every((value) => right.includes(value));
}

function artifactTime(artifact: TournamentPrediction) {
  const value = artifact.generated_at || artifact.input_data_as_of;
  const timestamp = value ? Date.parse(value) : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function deriveStateFromSchedule(schedule: WorldCupMatch[], artifact: TournamentPrediction | null): TournamentState {
  const completed = schedule.filter((item) => isCompleteStatus(item.status));
  const championshipRounds = new Set(['R32', 'R16', 'QF', 'SF', 'Final']);
  const remaining = schedule.filter((item) => championshipRounds.has(String(item.stage)) && !isCompleteStatus(item.status));
  const activeRound = ['group', 'R32', 'R16', 'QF', 'SF', 'Final'].find((round) =>
    schedule.some((row) => row.stage === round && !isCompleteStatus(row.status)),
  ) ?? 'complete';
  const activeRows = schedule.filter((row) => row.stage === activeRound);
  const alive = activeRound === 'complete'
    ? completed.filter((row) => row.stage === 'Final').flatMap((row) => [row.winner_team_id]).filter(isDisplayTeam)
    : Array.from(new Set(activeRows.flatMap((row) =>
        isCompleteStatus(row.status)
          ? [row.winner_team_id]
          : [row.home_team_id, row.away_team_id],
      ).filter(isDisplayTeam))).sort();
  return {
    requested_anchor: 'current',
    anchor_label: '当前赛况',
    as_of_time: latestTime(schedule) || artifact?.generated_at || null,
    active_round: activeRound,
    round_completed: activeRows.filter((row) => isCompleteStatus(row.status)).length,
    round_total: activeRows.length,
    completed_match_ids: completed.map((item) => item.match_id),
    remaining_match_ids: remaining.map((item) => item.match_id),
    predictable_match_ids: artifact?.match_predictions?.map((item) => item.match_id) ?? [],
    alive_teams: alive,
    eliminated_teams: [],
    locked_results: [],
    remaining_matches: [],
    schedule_snapshot_id: '',
    schedule_hash: artifact?.schedule_hash ?? '',
    validation_status: artifact ? 'ready' : 'invalid',
    validation_errors: [],
    validation_warnings: [],
  };
}

function normalizeModules(artifact: TournamentPrediction | null): Record<string, FeatureModuleStatus> {
  if (!artifact) {
    return Object.fromEntries(MODULE_ORDER.map((name) => [name, {
      enabled: false,
      status: 'not_connected',
      message: '当前没有可验证的预测结果，无法确认该模块已进入概率。',
      coverage: 0,
    }]));
  }
  const existing = artifact?.feature_modules ?? {};
  const result: Record<string, FeatureModuleStatus> = {};
  for (const name of MODULE_ORDER) result[name] = existing[name] ?? fallbackModule(name);
  if (artifact?.match_predictions?.some((row) => row.probability_components?.some((component) => component.name === 'strength'))) result.strength = { enabled: true, status: 'available', message: '球队长期实力已参与本次概率。', coverage: 1 };
  if (artifact?.match_predictions?.some((row) => row.probability_components?.some((component) => component.name === 'goals'))) result.goals = { enabled: true, status: 'available', message: '进球模型已参与本次概率。', coverage: 1 };
  if (liveChampionRows(artifact).length) {
    result.path = { enabled: true, status: 'available', message: '冠军概率由赛事路径模拟得到。', coverage: 1 };
  }
  return result;
}

function fallbackModule(name: string): FeatureModuleStatus {
  const partial = name === 'rules';
  return {
    enabled: partial,
    status: partial ? 'partial' : 'not_connected',
    coverage: partial ? 0.5 : 0,
    message: partial ? '淘汰赛基础规则参与路径模拟，纪律细节仍需补齐。' : '本次预测未使用该数据。',
  };
}

const PUBLIC_REPORT_FORBIDDEN_TERMS = [
  'artifact',
  'candidate',
  'seed',
  'model_config_hash',
  '透明试算',
  '结构化概率',
  '发布门禁',
  '发布门槛',
  '给 AI',
];

function usableAgentReport(report?: PredictionAgentReport | null) {
  if (!report) return null;
  const publicText = [
    report.title,
    report.abstract,
    report.headline,
    report.summary,
    report.methodology_note,
    report.data_disclosure,
    ...(report.sections ?? []).flatMap((section) => [section.title, section.body, ...(section.bullets ?? [])]),
    ...(report.caveats ?? []),
  ].join('\n');
  if (!report.title || !report.abstract) return null;
  if (PUBLIC_REPORT_FORBIDDEN_TERMS.some((term) => publicText.includes(term))) return null;
  return report;
}


function legacyPredictionPayload(artifact: TournamentPrediction | null) {
  if (!artifact) return false;
  return !usableAgentReport(artifact.prediction_report) || !artifact.data_sources?.length;
}

function dataSourceStatusText(status?: string) {
  return ({
    available: '已获取可用数据',
    ok: '已获取可用数据',
    partial: '部分可用',
    unconfigured: '数据源未配置',
    unmatched: '数据源已配置但未匹配到该场比赛',
    empty: '数据源已配置但未返回可用数据',
    failed: '获取失败',
    api_error: '接口调用失败',
    plan_restricted: '数据源套餐不支持当前赛事',
    data_unavailable: '数据暂不可用',
    invalid: '数据未通过校验',
    disabled: '数据源未启用',
  } as Record<string, string>)[String(status ?? '')] ?? '状态未知';
}

function firstRejectedReason<T>(...results: Array<PromiseSettledResult<T>>) {
  return results.find((item) => item.status === 'rejected')?.reason ?? null;
}

function debugDetail(error: unknown) {
  if (error && typeof error === 'object' && 'detail' in error) return (error as { detail: unknown }).detail;
  return error instanceof Error ? error.message : error;
}

function publicQualityMessage(artifact: TournamentPrediction) {
  const missing = new Set(artifact.data_quality_report?.missing ?? []);
  if (missing.has('verified_team_model_features_unavailable') || missing.has('alive_team_features_missing')) {
    return '当前参赛球队的真实模型特征尚未补齐，系统已停止生成冠军概率。';
  }
  if (missing.has('champion_probabilities_empty')) {
    return '本次模拟没有生成有效冠军概率，结果不会对外展示。';
  }
  return '本次生成结果未通过正式验证，不会作为冠军预测展示。';
}

function publicSourceMessage(status?: string, _message?: string) {
  return ({
    available: '该来源已返回可用数据。',
    ok: '该来源已返回可用数据，最终是否入模仍以字段校验结果为准。',
    partial: '该来源仅覆盖部分所需字段。',
    unconfigured: '当前环境没有配置该数据源所需的访问凭据。',
    disabled: '该数据源当前未启用。',
    unmatched: '数据源已连接，但没有匹配到当前比赛。',
    empty: '数据源请求成功，但没有返回可采用的数据。',
    failed: '该来源本次获取失败，相关字段未进入预测。',
    api_error: '该来源接口调用失败，相关字段未进入预测。',
    plan_restricted: '该数据源已经连接，但当前套餐不支持 2026 赛季；系统会保留这一限制并使用其他可追溯来源。',
    data_unavailable: '该来源没有形成可用于正式预测的数据。',
    invalid: '该来源数据未通过字段和质量校验。',
  } as Record<string, string>)[String(status ?? '')] ?? '该来源没有形成可验证的输入。';
}

function dataSourceLabel(sourceKey?: string) {
  const key = String(sourceKey ?? '');
  if (key.startsWith('live_squad_health:')) return `${teamName(key.split(':')[1])}阵容健康证据`;
  if (key.startsWith('api_football_odds:')) return 'API-Sports 赔率接口';
  if (key.startsWith('web_market_odds:')) return '联网赔率证据';
  if (key.startsWith('match_environment:')) return '比赛场馆与天气';
  if (key.startsWith('web_evidence:')) return '赛前新闻与阵容证据';
  return ({
    bing_sports_html_fragment: '世界杯实时赛程与赛果',
    fifa_live_mens_ranking: 'FIFA 男足排名',
    world_football_elo_live: '世界足球 Elo 评级',
    worldcup_completed_results_features: '本届世界杯近期状态与攻防',
    openfootball_worldcup_history_features: '世界杯历史经验',
  } as Record<string, string>)[key] ?? '外部数据来源';
}

function publicDebugMessage(issue: unknown) {
  if (!issue) return '无附加诊断信息';
  if (issue && typeof issue === 'object' && 'status' in issue) {
    const status = Number((issue as { status?: unknown }).status);
    if (status === 409) return '当前阶段没有通过验证的正式预测';
    if (status === 404) return '没有找到对应预测版本';
  }
  return '预测读取或生成未完成，请结合上方数据缺口处理';
}

function samplingError(probability: number, count: number) { return count > 0 ? 1.96 * Math.sqrt(probability * (1 - probability) / count) : 0; }
function safeNumber(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value : 0; }
function formatPercent(value: number | undefined | null) { const next = safeNumber(value); return `${(next * 100).toFixed(next < 0.01 ? 2 : 1)}%`; }
function formatDateTime(value?: string | null) { if (!value) return '暂无'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间待确认' : date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
function isCompleteStatus(status?: string | null) { return ['complete', 'completed', 'final', 'closed'].includes(String(status ?? '').toLowerCase()); }
function latestTime(schedule: WorldCupMatch[]) { return schedule.map((item) => item.fetched_at || item.kickoff_time).filter(Boolean).sort().at(-1) ?? null; }
function stageName(stage?: string | null) { return ({ group: '小组赛', R32: '32 强', R16: '16 强', QF: '八强', SF: '四强', Final: '决赛', ThirdPlace: '季军赛' } as Record<string, string>)[stage ?? ''] ?? stage ?? '阶段待定'; }
function componentName(name: string) { return ({ strength: '球队实力', goals: '进球模型', path: '赛程路径', market: '赔率盘口', web_semantic: '新闻语义', lineup: '阵容伤停', environment: '天气环境', rules: '规则约束', discipline: '黄牌纪律', tactical: '战术对位', neutral_prior: '中性先验' } as Record<string, string>)[name] ?? name; }
function moduleStatusLabel(status: string) { return status === 'available' ? '已接入' : status === 'partial' ? '部分接入' : '未接入'; }
function matchupLabel(row: ChampionProbability) { const match = row.key_matchups?.[0]; return match ? `${teamName(match.opponent_team_id)} / ${stageName(match.round)} / 相遇 ${formatPercent(match.encounter_probability)}` : row.potential_key_match || '暂无稳定项'; }
function humanMissing(value: string) { return ({ market_odds: '赔率盘口未接入', confirmed_lineup_or_injuries: '确认阵容和伤停未接入', fresh_web_evidence: '没有采用到可验证的最新网络证据', at_least_one_verified_external_source_status_ok: '缺少通过校验的外部数据源', schedule_sync_not_success: '赛程同步未成功', schedule_snapshot_stale: '赛程快照已过期', verified_team_model_features_unavailable: '真实球队模型特征尚未补齐', alive_team_features_missing: '存活球队缺少真实模型特征', champion_probabilities_empty: '没有生成有效冠军概率', current_tournament_state_mismatch: '预测版本与当前赛事状态不一致', data_quality_not_ready: '数据质量未达到正式展示条件' } as Record<string, string>)[value] ?? '存在未完成的数据校验项'; }
function adjustmentName(value: string) { return ({ lineup: '阵容修正', suspension: '停赛修正', fatigue: '体能修正', environment: '环境修正', tactical: '战术修正' } as Record<string, string>)[value] ?? '其他修正'; }
function teamName(teamId?: string | null) { if (!teamId) return ''; return TEAM_NAMES[teamId] ?? teamId; }

function modelAssumptions(prediction: MatchPrediction) {
  const items = [
    { title: '概率来源', text: '本场概率由球队实力、进球模型与中性先验融合得到；未接入的数据不会被补写成事实。' },
    { title: '淘汰赛处理', text: `常规时间平局概率为 ${formatPercent(prediction.draw_prob)}，最终晋级概率另行计入加时与点球路径。` },
  ];
  if (prediction.missing_fields?.includes('market_odds')) items.push({ title: '赔率边界', text: '赔率盘口未进入本次概率，页面不展示市场判断或历史命中率。' });
  if (prediction.missing_fields?.includes('confirmed_lineup_or_injuries')) items.push({ title: '阵容边界', text: '确认首发、伤停和停赛未完全入模，因此相关不确定性体现在置信度上限中。' });
  return items;
}

function isDisplayTeam(value?: string | null): value is string {
  const text = String(value ?? '').trim();
  return Boolean(text)
    && !/^[WL]\d{1,3}$/i.test(text)
    && !['TBD', 'TBC', 'UNKNOWN', 'N/A', 'NA'].includes(text.toUpperCase())
    && !['待定', '待确认', '未确定'].includes(text);
}

const TEAM_NAMES: Record<string, string> = {
  ALG: '阿尔及利亚', ARG: '阿根廷', AUS: '澳大利亚', AUT: '奥地利', BEL: '比利时', BIH: '波黑', BRA: '巴西',
  CAN: '加拿大', CIV: '科特迪瓦', COD: '刚果民主共和国', COL: '哥伦比亚', CPV: '佛得角', CRO: '克罗地亚',
  ECU: '厄瓜多尔', EGY: '埃及', ENG: '英格兰', ESP: '西班牙', FRA: '法国', GER: '德国', GHA: '加纳',
  IRN: '伊朗', IRQ: '伊拉克', JPN: '日本', KOR: '韩国', KSA: '沙特阿拉伯', MAR: '摩洛哥', MEX: '墨西哥',
  NED: '荷兰', NOR: '挪威', NZL: '新西兰', PAN: '巴拿马', PAR: '巴拉圭', POR: '葡萄牙', QAT: '卡塔尔',
  RSA: '南非', SCO: '苏格兰', SEN: '塞内加尔', SUI: '瑞士', SWE: '瑞典', TUN: '突尼斯', TUR: '土耳其',
  URU: '乌拉圭', USA: '美国', UZB: '乌兹别克斯坦',
};
