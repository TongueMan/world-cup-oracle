import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { AgentDrawer } from './components/AgentDrawer';
import { AppHeader } from './components/AppHeader';
import { api } from './lib/api';
import type {
  AgentPageContext,
  WorldCupHistoryEdition,
  WorldCupHistoryMatch,
  WorldCupMatch,
  WorldCupPlayerStat,
  WorldCupStanding,
  WorldCupSyncStatus,
} from './lib/types';

type TabKey = 'matches' | 'bracket' | 'standings' | 'stats' | 'history';
type StatTab = 'goals' | 'assists' | 'yellow' | 'red';
type HistoryViewMode = 'editions' | 'finals' | 'teams' | 'classic';
type RobotPose = 'idle' | 'wave' | 'stretch' | 'kick';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'matches', label: '比赛' },
  { key: 'bracket', label: '赛程表' },
  { key: 'standings', label: '排名' },
  { key: 'stats', label: '统计信息' },
  { key: 'history', label: '历史世界杯' },
];

const STAT_TABS: Array<{ key: StatTab; label: string }> = [
  { key: 'goals', label: '进球数' },
  { key: 'assists', label: '助攻' },
  { key: 'yellow', label: '黄牌' },
  { key: 'red', label: '红牌' },
];

const HISTORY_MODES: Array<{ key: HistoryViewMode; label: string }> = [
  { key: 'editions', label: '历届赛事' },
  { key: 'finals', label: '历届决赛' },
  { key: 'teams', label: '国家队战绩' },
  { key: 'classic', label: '经典淘汰赛' },
];

const ROBOT_POSES: RobotPose[] = ['wave', 'stretch', 'kick'];
const ROBOT_IMAGE_POSES: RobotPose[] = ['idle', 'wave', 'stretch', 'kick'];

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('matches');
  const [matches, setMatches] = useState<WorldCupMatch[]>([]);
  const [bracket, setBracket] = useState<WorldCupMatch[]>([]);
  const [standings, setStandings] = useState<WorldCupStanding[]>([]);
  const [stats, setStats] = useState<WorldCupPlayerStat[]>([]);
  const [historyEditions, setHistoryEditions] = useState<WorldCupHistoryEdition[]>([]);
  const [historyFinals, setHistoryFinals] = useState<WorldCupHistoryMatch[]>([]);
  const [historyMatches, setHistoryMatches] = useState<WorldCupHistoryMatch[]>([]);
  const [historyMode, setHistoryMode] = useState<HistoryViewMode>('editions');
  const [historyYear, setHistoryYear] = useState(2022);
  const [historyHomeTeam, setHistoryHomeTeam] = useState('');
  const [historyAwayTeam, setHistoryAwayTeam] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<WorldCupSyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentContext, setAgentContext] = useState<AgentPageContext>(defaultAgentContext('matches'));
  const [agentSessionKey, setAgentSessionKey] = useState('page:matches');
  const [agentPrompt, setAgentPrompt] = useState('');
  const [robotPose, setRobotPose] = useState<RobotPose>('idle');

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [status, matchRows, bracketRows, standingRows, statRows, editionRows, finalRows] = await Promise.all([
        api.getWorldCupSyncStatus(),
        api.getWorldCupMatches(),
        api.getWorldCupBracket(),
        api.getWorldCupStandings(),
        api.getWorldCupPlayerStats(),
        api.getWorldCupHistoryEditions(),
        api.getWorldCupHistoryFinals(),
      ]);
      setSyncStatus(status);
      setMatches(sortMatches(matchRows));
      setBracket(sortMatches(bracketRows));
      setStandings(standingRows);
      setStats(statRows);
      setHistoryEditions(editionRows);
      setHistoryFinals(finalRows);
      setHistoryYear(editionRows.at(-1)?.year ?? 2022);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      await api.syncWorldCup();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  }

  const loadHistoryMatches = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const homeTeam = historyHomeTeam.trim();
      const awayTeam = historyAwayTeam.trim();
      if (historyMode === 'teams') {
        setHistoryMatches(await api.getWorldCupHistoryMatches({ homeTeam, awayTeam }));
      } else if (historyMode === 'classic') {
        setHistoryMatches(await api.getWorldCupHistoryEditionMatches(historyYear, {
          stage: 'Final',
          homeTeam,
          awayTeam,
        }));
      } else {
        setHistoryMatches(await api.getWorldCupHistoryEditionMatches(historyYear));
      }
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : String(err));
    } finally {
      setHistoryLoading(false);
    }
  }, [historyAwayTeam, historyHomeTeam, historyMode, historyYear]);

  const pageAgentContext = useMemo(
    () => pageAgentContextForTab(activeTab, {
      matches,
      bracket,
      standings,
      stats,
      historyEditions,
      historyFinals,
      historyMatches,
      historyMode,
      historyYear,
    }),
    [activeTab, bracket, historyEditions, historyFinals, historyMatches, historyMode, historyYear, matches, standings, stats],
  );

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    setAgentContext(pageAgentContext);
    setAgentSessionKey(pageSessionKey(activeTab));
    if (activeTab !== 'matches') window.scrollTo({ top: 0, behavior: 'auto' });
  }, [activeTab, pageAgentContext]);

  useEffect(() => {
    if (activeTab !== 'history') return;
    void loadHistoryMatches();
  }, [activeTab, loadHistoryMatches]);

  useEffect(() => {
    let resetTimer: number | null = null;
    const interval = window.setInterval(() => {
      const nextPose = ROBOT_POSES[Math.floor(Math.random() * ROBOT_POSES.length)];
      setRobotPose(nextPose);
      if (resetTimer != null) window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => setRobotPose('idle'), 1600);
    }, 6200);
    return () => {
      window.clearInterval(interval);
      if (resetTimer != null) window.clearTimeout(resetTimer);
    };
  }, []);

  function openAgent(prompt: string, context: AgentPageContext = pageAgentContext, sessionKey = sessionKeyForContext(context)) {
    setAgentPrompt(prompt);
    setAgentContext(context);
    setAgentSessionKey(sessionKey);
    setAgentOpen(true);
  }

  const completeCount = matches.filter((match) => match.status === 'complete').length;
  const scheduledCount = matches.filter((match) => match.status === 'scheduled').length;
  return (
    <div className="app-shell min-h-screen bg-[#07140b] text-white">
      <div className="stadium-backdrop" />
      <AppHeader syncStatus={syncStatus} syncing={syncing} onSync={handleSync} />

      <main className="app-main relative mx-auto max-w-7xl space-y-6 px-4 pb-8 sm:px-6 lg:px-8">
        <section className="hero-field overflow-hidden rounded-[28px] border border-white/15">
          <div className="grid gap-6 p-5 sm:p-7 lg:grid-cols-[1.05fr_0.95fr] lg:p-8">
            <div>
              <p className="text-xs font-semibold tracking-[0.24em] text-[#ffe18a]">2026 世界杯实时赛程</p>
              <h2 className="mt-4 max-w-3xl text-4xl font-black leading-tight text-white sm:text-5xl">
                世界杯赛程、预测与历史数据指挥舱
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-white/78">
                集中查看比赛结果、淘汰赛路径、小组排名、球员统计和历届世界杯数据。
              </p>
              <div className="mt-8 grid gap-3 sm:grid-cols-4">
                <Metric label="比赛" value={`${matches.length}`} />
                <Metric label="已赛" value={`${completeCount}`} />
                <Metric label="未赛" value={`${scheduledCount}`} />
                <Metric label="排名" value={`${standings.length}`} />
              </div>
            </div>
            <div className="pitch-board">
              <div className="pitch-line center-circle" />
              <div className="pitch-line halfway" />
              <div className="goal-box left" />
              <div className="goal-box right" />
              <div className="football-mark" />
            </div>
          </div>
        </section>

        {error && <div className="rounded-2xl border border-rose-200/30 bg-rose-500/12 p-4 text-sm text-rose-50">{error}</div>}

        <section className={`oracle-panel p-4 sm:p-5 ${activeTab === 'bracket' ? 'oracle-panel-wide' : ''}`}>
          <div className="page-tabs -mx-4 mb-5 flex flex-wrap gap-2 border-b border-white/10 bg-[#08210f]/92 px-4 py-3 backdrop-blur sm:-mx-5 sm:px-5">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`rounded-xl border px-4 py-2 text-sm font-bold transition ${
                  activeTab === tab.key
                    ? 'border-[#ffe18a]/60 bg-[#ffe18a]/18 text-[#ffe18a]'
                    : 'border-white/12 bg-white/8 text-white/68 hover:bg-white/12'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="page-content">
            {loading ? (
              <div className="flex min-h-64 items-center justify-center">
                <div className="football-spinner" />
              </div>
            ) : (
              <>
                {activeTab === 'matches' && <MatchesView matches={matches} onAnalyze={(match) => openAgent(matchAnalysisPrompt(match), matchAgentContext(match, activeTab))} />}
                {activeTab === 'bracket' && <BracketView matches={bracket} onAnalyze={(match) => openAgent(matchAnalysisPrompt(match), matchAgentContext(match, activeTab))} />}
                {activeTab === 'standings' && <StandingsView standings={standings} />}
                {activeTab === 'stats' && <StatsView stats={stats} />}
                {activeTab === 'history' && (
                  <HistoryView
                    editions={historyEditions}
                    finals={historyFinals}
                    matches={historyMatches}
                    mode={historyMode}
                    selectedYear={historyYear}
                    homeTeamQuery={historyHomeTeam}
                    awayTeamQuery={historyAwayTeam}
                    loading={historyLoading}
                    error={historyError}
                    onModeChange={setHistoryMode}
                    onYearChange={setHistoryYear}
                    onHomeTeamQueryChange={setHistoryHomeTeam}
                    onAwayTeamQueryChange={setHistoryAwayTeam}
                  />
                )}
              </>
            )}
          </div>
        </section>
      </main>

      <button
        type="button"
        className={`agent-floating-button robot-pose-${robotPose}`}
        aria-label="打开世界杯 AI 助手"
        onClick={() => openAgent('我想围绕当前页面提问。', pageAgentContext, pageSessionKey(activeTab))}
      >
        <span className="agent-robot-frame" aria-hidden="true">
          {ROBOT_IMAGE_POSES.map((pose) => (
            <img
              key={pose}
              src={`/assets/ai-football-robot-${pose}.png`}
              alt=""
              className={pose === robotPose ? 'active' : ''}
            />
          ))}
        </span>
      </button>
      <AgentDrawer
        open={agentOpen}
        sessionKey={agentSessionKey}
        context={agentContext}
        initialPrompt={agentPrompt}
        onClose={() => setAgentOpen(false)}
      />
    </div>
  );
}

function MatchesView({ matches, onAnalyze }: { matches: WorldCupMatch[]; onAnalyze: (match: WorldCupMatch) => void }) {
  const groups = useMemo(() => groupMatchesByDate(matches), [matches]);
  const todayKey = useMemo(() => nearestMatchDateKey(groups), [groups]);
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    const target = todayKey ? sectionRefs.current[todayKey] : null;
    if (target) target.scrollIntoView({ block: 'start' });
  }, [todayKey]);

  return (
    <div className="space-y-7">
      {groups.map(([date, rows]) => (
        <div key={date} className="match-date-section" ref={(node) => { sectionRefs.current[date] = node; }}>
          <h3 className="mb-3 text-base font-black text-[#ffe18a]">{date}</h3>
          <div className="grid overflow-hidden rounded-3xl border border-white/10 bg-[#f4efea]/95 text-[#171c18] md:grid-cols-2">
            {rows.map((match) => <MatchCard key={match.match_id} match={match} light onAnalyze={onAnalyze} />)}
          </div>
        </div>
      ))}
      {groups.length === 0 && <EmptyState text="暂无比赛数据。" />}
    </div>
  );
}

function BracketView({ matches, onAnalyze }: { matches: WorldCupMatch[]; onAnalyze: (match: WorldCupMatch) => void }) {
  const layout = buildBracketLayout(matches);
  if (matches.length === 0) return <EmptyState text="暂无赛程表数据。" />;

  return (
    <div className="relative left-1/2 w-screen -translate-x-1/2 overflow-x-auto bg-white py-5 text-[#121712]">
      <div className="relative mx-auto" style={{ width: layout.width, height: layout.height }}>
        <div className="absolute left-0 right-0 top-0 text-sm font-black">
          {layout.headers.map((header) => (
            <div
              key={header.key}
              className="text-center text-sm font-black"
              style={{ position: 'absolute', left: header.x, top: 0, width: header.width }}
            >
              {header.label}
            </div>
          ))}
        </div>
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          aria-hidden="true"
        >
          {layout.links.map((link) => (
            <path
              key={link.key}
              d={link.d}
              fill="none"
              stroke="#c9c9c9"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </svg>
        {layout.cards.map((card) => (
          <div
            key={card.key}
            className="absolute"
            style={{ left: card.x, top: card.y, width: card.width }}
          >
            <MatchCard match={card.match} light compact onAnalyze={onAnalyze} />
          </div>
        ))}
      </div>
    </div>
  );
}

function StandingsView({ standings }: { standings: WorldCupStanding[] }) {
  const groups = useMemo(() => groupBy(standings, (row) => row.group_name ?? '未分组'), [standings]);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {Object.entries(groups).map(([group, rows]) => (
        <div key={group} className="rounded-3xl border border-white/12 bg-[#f4efea]/95 p-5 text-[#151a16]">
          <h3 className="mb-4 text-xl font-black">{group}</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead className="text-[#6d716b]">
                <tr>
                  <th className="py-2 text-left">球队</th>
                  <th>场次</th>
                  <th>胜</th>
                  <th>平</th>
                  <th>负</th>
                  <th>进球</th>
                  <th>失球</th>
                  <th>净胜</th>
                  <th>得分</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={row.id} className="border-t border-black/10">
                    <td className="py-3 font-bold">
                      <span className="mr-2 text-[#70756f]">{index + 1}</span>
                      <FlagIcon teamId={row.team_id} teamName={row.team_name_raw} />
                      {displayTeamName(row.team_name_raw)}
                    </td>
                    <td className="text-center">{row.played ?? '-'}</td>
                    <td className="text-center">{row.won ?? '-'}</td>
                    <td className="text-center">{row.drawn ?? '-'}</td>
                    <td className="text-center">{row.lost ?? '-'}</td>
                    <td className="text-center">{row.goals_for ?? '-'}</td>
                    <td className="text-center">{row.goals_against ?? '-'}</td>
                    <td className="text-center">{row.goal_difference ?? '-'}</td>
                    <td className="text-center font-black">{row.points ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function StatsView({ stats }: { stats: WorldCupPlayerStat[] }) {
  const [activeStat, setActiveStat] = useState<StatTab>('goals');
  const rows = useMemo(() => splitStats(stats)[activeStat].slice(0, 20), [stats, activeStat]);
  const valueLabel = STAT_TABS.find((tab) => tab.key === activeStat)?.label ?? '数值';

  return (
    <div className="mx-auto max-w-3xl rounded-3xl bg-[#f4efea]/95 p-5 text-[#151a16]">
      <div className="mb-4 flex flex-wrap gap-2">
        {STAT_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveStat(tab.key)}
            className={`rounded-xl px-4 py-2 text-sm font-bold ${
              activeStat === tab.key ? 'bg-[#dbe3ff] text-[#3153d7]' : 'bg-white/60 text-[#333]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="mb-2 grid grid-cols-[1fr_80px] px-2 text-sm font-bold text-[#70756f]">
        <span>球员</span>
        <span className="text-right">{valueLabel}</span>
      </div>
      <div className="divide-y divide-black/10">
        {rows.map((stat, index) => (
          <div key={`${stat.title ?? index}-${index}`} className="grid grid-cols-[1fr_80px] items-center gap-3 py-3">
            <div className="flex min-w-0 items-center gap-3">
              {stat.image_url ? (
                <img src={stat.image_url} alt="" className="h-11 w-11 rounded-full object-cover" />
              ) : (
                <div className="h-11 w-11 rounded-full bg-white" />
              )}
              <div className="min-w-0">
                <div className="truncate font-black">{playerName(stat)}</div>
                <div className="truncate text-xs text-[#70756f]">{displayTeamName(playerTeam(stat))}</div>
              </div>
            </div>
            <div className="text-right text-lg font-black">{stat.value ?? '-'}</div>
          </div>
        ))}
      </div>
      {rows.length === 0 && <EmptyState text="暂无统计信息。" />}
    </div>
  );
}

function HistoryView({
  editions,
  finals,
  matches,
  mode,
  selectedYear,
  homeTeamQuery,
  awayTeamQuery,
  loading,
  error,
  onModeChange,
  onYearChange,
  onHomeTeamQueryChange,
  onAwayTeamQueryChange,
}: {
  editions: WorldCupHistoryEdition[];
  finals: WorldCupHistoryMatch[];
  matches: WorldCupHistoryMatch[];
  mode: HistoryViewMode;
  selectedYear: number;
  homeTeamQuery: string;
  awayTeamQuery: string;
  loading: boolean;
  error: string | null;
  onModeChange: (mode: HistoryViewMode) => void;
  onYearChange: (year: number) => void;
  onHomeTeamQueryChange: (team: string) => void;
  onAwayTeamQueryChange: (team: string) => void;
}) {
  const selectedEdition = editions.find((edition) => edition.year === selectedYear) ?? editions.at(-1);
  const rows = mode === 'finals' ? filterHistoryMatchesBySide(finals, homeTeamQuery, awayTeamQuery) : matches;
  const showTeamSearch = mode === 'finals' || mode === 'teams' || mode === 'classic';
  const hasTeamSearch = Boolean(homeTeamQuery.trim() || awayTeamQuery.trim());

  return (
    <div className="history-view">
      <div className="history-toolbar">
        <div className="history-mode-tabs">
          {HISTORY_MODES.map((item) => (
            <button key={item.key} type="button" onClick={() => onModeChange(item.key)} className={mode === item.key ? 'active' : ''}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="history-filters">
          {(mode === 'editions' || mode === 'classic') && (
            <select value={selectedYear} onChange={(event) => onYearChange(Number(event.target.value))}>
              {editions.map((edition) => <option key={edition.year} value={edition.year}>{edition.year}</option>)}
            </select>
          )}
          {showTeamSearch && (
            <div className="history-team-search" aria-label="历史比赛主客队搜索">
              <input value={homeTeamQuery} onChange={(event) => onHomeTeamQueryChange(event.target.value)} placeholder="主队" />
              <input value={awayTeamQuery} onChange={(event) => onAwayTeamQueryChange(event.target.value)} placeholder="客队" />
              {hasTeamSearch && (
                <button
                  type="button"
                  className="history-filter-clear"
                  onClick={() => {
                    onHomeTeamQueryChange('');
                    onAwayTeamQueryChange('');
                  }}
                >
                  清空
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {error && <div className="history-error">{error}</div>}

      {mode === 'editions' && (
        <div className="history-editions-grid">
          {editions.map((edition) => (
            <button
              key={edition.year}
              type="button"
              className={`history-edition-card ${edition.year === selectedYear ? 'active' : ''}`}
              onClick={() => onYearChange(edition.year)}
            >
              <span>{edition.year}</span>
              <strong>
                <FlagIcon flagCode={edition.champion_flag_code} />
                {historyTeamName(edition.champion, edition.champion_zh)}
              </strong>
              <small>{historyHostNames(edition).join(' / ')} · {edition.match_count} 场</small>
            </button>
          ))}
        </div>
      )}

      {mode === 'editions' && selectedEdition && (
        <div className="history-summary-band">
          <div>
            <span>{selectedEdition.year}</span>
            <strong>
              <FlagIcon flagCode={selectedEdition.champion_flag_code} />
              {historyTeamName(selectedEdition.champion, selectedEdition.champion_zh)}
            </strong>
            <small>冠军</small>
          </div>
          <div>
            <span>
              <FlagIcon flagCode={selectedEdition.runner_up_flag_code} />
              {historyTeamName(selectedEdition.runner_up, selectedEdition.runner_up_zh)}
            </span>
            <strong>{historyHostNames(selectedEdition).join(' / ')}</strong>
            <small>亚军 / 主办</small>
          </div>
          <div>
            <span>{selectedEdition.team_count} 支球队</span>
            <strong>{selectedEdition.match_count} 场比赛</strong>
            <small>{selectedEdition.start_date} - {selectedEdition.end_date}</small>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex min-h-48 items-center justify-center">
          <div className="football-spinner" />
        </div>
      ) : (
        <HistoryMatchTable rows={rows} compact={mode === 'finals' || mode === 'classic'} />
      )}
    </div>
  );
}

function HistoryMatchTable({ rows, compact = false }: { rows: WorldCupHistoryMatch[]; compact?: boolean }) {
  const displayRows = compact ? rows : rows.slice(0, 80);
  return (
    <div className="history-table-wrap">
      <table className="history-table">
        <thead>
          <tr>
            <th>年份</th>
            <th>阶段</th>
            <th>日期</th>
            <th>比赛</th>
            <th>比分</th>
            <th>场地</th>
          </tr>
        </thead>
        <tbody>
          {displayRows.map((match) => (
            <tr key={match.match_id}>
              <td>{match.year}</td>
              <td>{historyStageName(match)}</td>
              <td>{match.date ?? '-'}</td>
              <td>
                <strong>
                  <FlagIcon flagCode={match.home_flag_code} />
                  {historyTeamName(match.home_team, match.home_team_zh)}
                </strong>
                <span> vs </span>
                <strong>
                  <FlagIcon flagCode={match.away_flag_code} />
                  {historyTeamName(match.away_team, match.away_team_zh)}
                </strong>
              </td>
              <td>{historyScore(match)}</td>
              <td>{historyVenue(match)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <EmptyState text="暂无历史比赛数据。" />}
      {!compact && rows.length > displayRows.length && <div className="history-more-note">已显示前 {displayRows.length} 场</div>}
    </div>
  );
}

function MatchCard({
  match,
  compact = false,
  light = false,
  onAnalyze,
}: {
  match: WorldCupMatch;
  compact?: boolean;
  light?: boolean;
  onAnalyze?: (match: WorldCupMatch) => void;
}) {
  const cardClass = light
    ? 'border-black/8 bg-[#f4efea] text-[#151a16]'
    : 'border-white/12 bg-[#08210f]/74 text-white';
  const sizingClass = compact ? 'h-[112px] overflow-hidden p-3' : 'p-4';
  const clickableClass = compact && onAnalyze ? 'cursor-pointer transition hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#d5b856]' : '';
  const handleCompactKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!compact || !onAnalyze || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    onAnalyze(match);
  };

  return (
    <div
      className={`border ${sizingClass} ${cardClass} ${clickableClass}`}
      role={compact && onAnalyze ? 'button' : undefined}
      tabIndex={compact && onAnalyze ? 0 : undefined}
      onClick={compact && onAnalyze ? () => onAnalyze(match) : undefined}
      onKeyDown={handleCompactKeyDown}
    >
      <div className="mb-3 flex items-center justify-between gap-3 text-xs opacity-70">
        <span>{matchLabel(match)}</span>
        <span>{match.status === 'complete' ? '全场' : formatMatchTime(match)}</span>
      </div>
      <TeamLine
        teamId={match.home_team_id}
        name={match.home_team_raw}
        score={match.home_score}
        penalty={match.home_penalty}
        winner={match.winner_team_id === match.home_team_id}
      />
      <TeamLine
        teamId={match.away_team_id}
        name={match.away_team_raw}
        score={match.away_score}
        penalty={match.away_penalty}
        winner={match.winner_team_id === match.away_team_id}
      />
      {!compact && match.next_match_id && (
        <div className="mt-3 truncate border-t border-black/10 pt-3 text-xs opacity-55">
          胜者晋级：{shortMatchId(match.next_match_id)}
        </div>
      )}
      {!compact && onAnalyze && (
        <button
          type="button"
          className="mt-3 rounded-lg border border-black/10 bg-white/55 px-3 py-1.5 text-xs font-black text-[#172015] transition hover:bg-white"
          onClick={() => onAnalyze(match)}
        >
          分析这场
        </button>
      )}
    </div>
  );
}

function TeamLine({
  teamId,
  name,
  score,
  penalty,
  winner,
}: {
  teamId: string | null;
  name: string | null;
  score: number | null;
  penalty: number | null;
  winner: boolean;
}) {
  return (
    <div className={`flex items-center gap-3 py-1.5 ${winner ? 'font-black' : ''}`}>
      <FlagIcon teamId={teamId} teamName={name} />
      <span className={`min-w-0 flex-1 whitespace-nowrap font-bold ${teamNameTextSize(name ?? teamId ?? '')}`}>
        {displayTeamName(name ?? teamId ?? '待定')}
      </span>
      <span className="w-8 text-right text-lg font-black">{score ?? ''}</span>
      {penalty != null && <span className="w-8 text-right text-sm opacity-65">({penalty})</span>}
    </div>
  );
}

function FlagIcon({
  teamId,
  teamName,
  flagCode,
}: {
  teamId?: string | null;
  teamName?: string | null;
  flagCode?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  const src = flagUrlForTeam(teamId, teamName, flagCode);
  if (!src || failed) {
    return <span className="history-flag-fallback mr-2 inline-block h-4 w-6 rounded-sm border border-black/10 align-[-2px]" />;
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className="mr-2 inline-block h-4 w-6 rounded-[2px] border border-black/10 object-cover align-[-2px] shadow-sm"
    />
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/15 bg-black/28 p-4 backdrop-blur">
      <div className="text-xs text-white/55">{label}</div>
      <div className="mt-1 text-2xl font-black text-white">{value}</div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed border-black/18 bg-white/40 p-4 text-sm text-black/55">{text}</div>;
}

function groupMatchesByDate(matches: WorldCupMatch[]) {
  return Object.entries(groupBy(sortMatches(matches), displayDateKey));
}

function sortMatches(matches: WorldCupMatch[]) {
  return [...matches].sort((a, b) => matchSortValue(a) - matchSortValue(b));
}

function matchSortValue(match: WorldCupMatch) {
  const parsed = parseDateFromLabel(match.kickoff_label);
  if (parsed) return parsed.getTime();
  if (match.kickoff_time) return new Date(match.kickoff_time).getTime();
  return Number.MAX_SAFE_INTEGER;
}

function displayDateKey(match: WorldCupMatch) {
  const normalized = normalizeRelativeKickoffLabel(match.kickoff_label);
  const label = normalized?.match(/\d{1,2}月\d{1,2}日周./)?.[0];
  if (label) return label;
  if (match.kickoff_time) {
    return new Date(match.kickoff_time).toLocaleDateString('zh-CN', {
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    });
  }
  return '日期待定';
}

function nearestMatchDateKey(groups: Array<[string, WorldCupMatch[]]>) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let fallback = groups[0]?.[0] ?? '';
  for (const [key, rows] of groups) {
    const value = parseDateFromLabel(key) ?? (rows[0]?.kickoff_time ? new Date(rows[0].kickoff_time) : null);
    if (!value) continue;
    value.setHours(0, 0, 0, 0);
    if (value.getTime() >= today.getTime()) return key;
    fallback = key;
  }
  return fallback;
}

function parseDateFromLabel(label: string | null | undefined) {
  const normalized = normalizeRelativeKickoffLabel(label);
  if (!normalized) return null;
  const match = normalized.match(/(\d{1,2})月(\d{1,2})日/);
  if (!match) return null;
  return new Date(2026, Number(match[1]) - 1, Number(match[2]));
}

function formatMatchTime(match: WorldCupMatch) {
  const normalized = normalizeRelativeKickoffLabel(match.kickoff_label);
  if (normalized) {
    const time = normalized.match(/\d{1,2}:\d{2}/)?.[0];
    if (time) return time;
  }
  return formatDateTime(match.kickoff_time) || normalized || match.kickoff_label || '';
}

function normalizeRelativeKickoffLabel(label: string | null | undefined) {
  if (!label) return '';
  const relative = label.match(/^(昨天|今天|明天)(.*)$/);
  if (!relative) return label;
  const offset = relative[1] === '昨天' ? -1 : relative[1] === '明天' ? 1 : 0;
  const base = new Date();
  base.setDate(base.getDate() + offset);
  return `${formatChineseDate(base)}${relative[2] ?? ''}`;
}

function formatChineseDate(date: Date) {
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  return `${date.getMonth() + 1}月${date.getDate()}日${weekdays[date.getDay()]}`;
}

type BracketCardNode = {
  key: string;
  match: WorldCupMatch;
  x: number;
  y: number;
  width: number;
};

type BracketHeaderNode = {
  key: string;
  label: string;
  x: number;
  width: number;
};

type BracketConnector = {
  key: string;
  d: string;
};

type BracketLayoutConfig = {
  width: number;
  height: number;
  cardWidth: number;
  finalWidth: number;
  cardHeight: number;
  leftX: Record<'R32' | 'R16' | 'QF' | 'SF' | 'Final', number>;
  rightX: Record<'R32' | 'R16' | 'QF' | 'SF', number>;
  y: Record<'R32' | 'R16' | 'QF' | 'SF' | 'Final', number[]>;
};

const BRACKET_LAYOUT: BracketLayoutConfig = {
  width: 2520,
  height: 1160,
  cardWidth: 196,
  finalWidth: 260,
  cardHeight: 112,
  leftX: {
    R32: 80,
    R16: 340,
    QF: 600,
    SF: 850,
    Final: 1103,
  },
  rightX: {
    SF: 1420,
    QF: 1670,
    R16: 1930,
    R32: 2220,
  },
  y: {
    R32: [78, 208, 338, 468, 598, 728, 858, 988],
    R16: [143, 403, 663, 923],
    QF: [273, 793],
    SF: [533],
    Final: [533],
  },
};

function buildBracketLayout(matches: WorldCupMatch[]) {
  const layout = BRACKET_LAYOUT;
  const cards: BracketCardNode[] = [];
  const links: BracketConnector[] = [];
  const sortedMatches = sortMatches(matches);

  const addCard = (key: string, match: WorldCupMatch, xPos: number, yPos: number, width = layout.cardWidth) => {
    if (yPos == null) return;
    cards.push({ key, match, x: xPos, y: yPos, width });
  };

  const final = sortedMatches.find((match) => match.stage === 'Final');
  const childrenOf = (match: WorldCupMatch | undefined, stage?: string) => {
    if (!match) return [];
    return sortMatches(
      sortedMatches.filter((row) => row.next_match_id === match.match_id && (!stage || row.stage === stage)),
    );
  };

  const semifinals = childrenOf(final, 'SF');
  const leftSF = semifinals[0];
  const rightSF = semifinals[1];
  const leftQF = childrenOf(leftSF, 'QF');
  const rightQF = childrenOf(rightSF, 'QF');
  const leftR16 = leftQF.flatMap((match) => childrenOf(match, 'R16'));
  const rightR16 = rightQF.flatMap((match) => childrenOf(match, 'R16'));
  const leftR32 = leftR16.flatMap((match) => childrenOf(match, 'R32'));
  const rightR32 = rightR16.flatMap((match) => childrenOf(match, 'R32'));

  leftR32.forEach((match, index) => addCard(`left-r32-${match.match_id}`, match, layout.leftX.R32, layout.y.R32[index]));
  leftR16.forEach((match, index) => addCard(`left-r16-${match.match_id}`, match, layout.leftX.R16, layout.y.R16[index]));
  leftQF.forEach((match, index) => addCard(`left-qf-${match.match_id}`, match, layout.leftX.QF, layout.y.QF[index]));
  if (leftSF) addCard(`left-sf-${leftSF.match_id}`, leftSF, layout.leftX.SF, layout.y.SF[0]);
  if (final) addCard(`final-${final.match_id}`, final, layout.leftX.Final, layout.y.Final[0], layout.finalWidth);
  if (rightSF) addCard(`right-sf-${rightSF.match_id}`, rightSF, layout.rightX.SF, layout.y.SF[0]);
  rightQF.forEach((match, index) => addCard(`right-qf-${match.match_id}`, match, layout.rightX.QF, layout.y.QF[index]));
  rightR16.forEach((match, index) => addCard(`right-r16-${match.match_id}`, match, layout.rightX.R16, layout.y.R16[index]));
  rightR32.forEach((match, index) => addCard(`right-r32-${match.match_id}`, match, layout.rightX.R32, layout.y.R32[index]));

  if (cards.length <= (final ? 1 : 0) && sortedMatches.length > 1) {
    return buildRoundFallbackBracketLayout(sortedMatches);
  }

  addBracketConnectors(links, layout, {
    leftR32: leftR32.length,
    leftR16: leftR16.length,
    leftQF: leftQF.length,
    leftSF: Boolean(leftSF),
    final: Boolean(final),
    rightSF: Boolean(rightSF),
    rightQF: rightQF.length,
    rightR16: rightR16.length,
    rightR32: rightR32.length,
  });

  return {
    width: layout.width,
    height: layout.height,
    headers: bracketHeaders(layout),
    cards,
    links,
  };
}

function buildRoundFallbackBracketLayout(matches: WorldCupMatch[]) {
  const layout = BRACKET_LAYOUT;
  const cards: BracketCardNode[] = [];
  const links: BracketConnector[] = [];
  const byStage = {
    R32: sortMatches(matches.filter((match) => match.stage === 'R32')),
    R16: sortMatches(matches.filter((match) => match.stage === 'R16')),
    QF: sortMatches(matches.filter((match) => match.stage === 'QF')),
    SF: sortMatches(matches.filter((match) => match.stage === 'SF')),
    Final: sortMatches(matches.filter((match) => match.stage === 'Final')),
  };
  const split = <T,>(items: T[]) => [items.slice(0, Math.ceil(items.length / 2)), items.slice(Math.ceil(items.length / 2))];
  const [leftR32, rightR32] = split(byStage.R32);
  const [leftR16, rightR16] = split(byStage.R16);
  const [leftQF, rightQF] = split(byStage.QF);
  const [leftSF, rightSF] = split(byStage.SF);
  const addCard = (key: string, match: WorldCupMatch, xPos: number, yPos: number, width = layout.cardWidth) => {
    if (yPos == null) return;
    cards.push({ key, match, x: xPos, y: yPos, width });
  };

  leftR32.forEach((match, index) => addCard(`fallback-left-r32-${match.match_id}`, match, layout.leftX.R32, layout.y.R32[index]));
  leftR16.forEach((match, index) => addCard(`fallback-left-r16-${match.match_id}`, match, layout.leftX.R16, layout.y.R16[index]));
  leftQF.forEach((match, index) => addCard(`fallback-left-qf-${match.match_id}`, match, layout.leftX.QF, layout.y.QF[index]));
  leftSF.forEach((match, index) => addCard(`fallback-left-sf-${match.match_id}`, match, layout.leftX.SF, layout.y.SF[index]));
  if (byStage.Final[0]) addCard(`fallback-final-${byStage.Final[0].match_id}`, byStage.Final[0], layout.leftX.Final, layout.y.Final[0], layout.finalWidth);
  rightSF.forEach((match, index) => addCard(`fallback-right-sf-${match.match_id}`, match, layout.rightX.SF, layout.y.SF[index]));
  rightQF.forEach((match, index) => addCard(`fallback-right-qf-${match.match_id}`, match, layout.rightX.QF, layout.y.QF[index]));
  rightR16.forEach((match, index) => addCard(`fallback-right-r16-${match.match_id}`, match, layout.rightX.R16, layout.y.R16[index]));
  rightR32.forEach((match, index) => addCard(`fallback-right-r32-${match.match_id}`, match, layout.rightX.R32, layout.y.R32[index]));

  addBracketConnectors(links, layout, {
    leftR32: leftR32.length,
    leftR16: leftR16.length,
    leftQF: leftQF.length,
    leftSF: leftSF.length > 0,
    final: byStage.Final.length > 0,
    rightSF: rightSF.length > 0,
    rightQF: rightQF.length,
    rightR16: rightR16.length,
    rightR32: rightR32.length,
  });

  return {
    width: layout.width,
    height: layout.height,
    headers: bracketHeaders(layout),
    cards,
    links,
  };
}

function addBracketConnectors(
  links: BracketConnector[],
  layout: BracketLayoutConfig,
  counts: {
    leftR32: number;
    leftR16: number;
    leftQF: number;
    leftSF: boolean;
    final: boolean;
    rightSF: boolean;
    rightQF: number;
    rightR16: number;
    rightR32: number;
  },
) {
  const centerOf = (yPos: number) => yPos + layout.cardHeight / 2;
  const addLeftPairLinks = (fromX: number, fromYs: number[], toX: number, toYs: number[], key: string) => {
    for (let index = 0; index < toYs.length; index += 1) {
      const y1 = fromYs[index * 2];
      const y2 = fromYs[index * 2 + 1];
      const targetY = toYs[index];
      if (y1 == null || y2 == null || targetY == null) continue;
      const sourceX = fromX + layout.cardWidth;
      const joinX = sourceX + 42;
      const sourceY1 = centerOf(y1);
      const sourceY2 = centerOf(y2);
      const targetCenterY = centerOf(targetY);
      links.push({
        key: `${key}-${index}`,
        d: [
          `M ${sourceX} ${sourceY1} H ${joinX}`,
          `M ${sourceX} ${sourceY2} H ${joinX}`,
          `M ${joinX} ${sourceY1} V ${sourceY2}`,
          `M ${joinX} ${targetCenterY} H ${toX}`,
        ].join(' '),
      });
    }
  };
  const addRightPairLinks = (fromX: number, fromYs: number[], toX: number, toYs: number[], key: string) => {
    for (let index = 0; index < toYs.length; index += 1) {
      const y1 = fromYs[index * 2];
      const y2 = fromYs[index * 2 + 1];
      const targetY = toYs[index];
      if (y1 == null || y2 == null || targetY == null) continue;
      const sourceX = fromX;
      const joinX = sourceX - 42;
      const targetX = toX + layout.cardWidth;
      const sourceY1 = centerOf(y1);
      const sourceY2 = centerOf(y2);
      const targetCenterY = centerOf(targetY);
      links.push({
        key: `${key}-${index}`,
        d: [
          `M ${sourceX} ${sourceY1} H ${joinX}`,
          `M ${sourceX} ${sourceY2} H ${joinX}`,
          `M ${joinX} ${sourceY1} V ${sourceY2}`,
          `M ${joinX} ${targetCenterY} H ${targetX}`,
        ].join(' '),
      });
    }
  };

  addLeftPairLinks(layout.leftX.R32, layout.y.R32.slice(0, counts.leftR32), layout.leftX.R16, layout.y.R16.slice(0, counts.leftR16), 'left-r32-r16');
  addLeftPairLinks(layout.leftX.R16, layout.y.R16.slice(0, counts.leftR16), layout.leftX.QF, layout.y.QF.slice(0, counts.leftQF), 'left-r16-qf');
  addLeftPairLinks(layout.leftX.QF, layout.y.QF.slice(0, counts.leftQF), layout.leftX.SF, counts.leftSF ? layout.y.SF : [], 'left-qf-sf');
  if (counts.leftSF && counts.final) {
    links.push({
      key: 'left-sf-final',
      d: `M ${layout.leftX.SF + layout.cardWidth} ${centerOf(layout.y.SF[0])} H ${layout.leftX.Final}`,
    });
  }

  addRightPairLinks(layout.rightX.R32, layout.y.R32.slice(0, counts.rightR32), layout.rightX.R16, layout.y.R16.slice(0, counts.rightR16), 'right-r32-r16');
  addRightPairLinks(layout.rightX.R16, layout.y.R16.slice(0, counts.rightR16), layout.rightX.QF, layout.y.QF.slice(0, counts.rightQF), 'right-r16-qf');
  addRightPairLinks(layout.rightX.QF, layout.y.QF.slice(0, counts.rightQF), layout.rightX.SF, counts.rightSF ? layout.y.SF : [], 'right-qf-sf');
  if (counts.rightSF && counts.final) {
    links.push({
      key: 'right-sf-final',
      d: `M ${layout.rightX.SF} ${centerOf(layout.y.SF[0])} H ${layout.leftX.Final + layout.finalWidth}`,
    });
  }
}

function bracketHeaders(layout: BracketLayoutConfig): BracketHeaderNode[] {
  return [
    { key: 'left-r32', label: '32 强赛', x: layout.leftX.R32, width: layout.cardWidth },
    { key: 'left-r16', label: '16 强赛', x: layout.leftX.R16, width: layout.cardWidth },
    { key: 'left-qf', label: '四分之一决赛', x: layout.leftX.QF, width: layout.cardWidth },
    { key: 'left-sf', label: '半决赛', x: layout.leftX.SF, width: layout.cardWidth },
    { key: 'final', label: '决赛', x: layout.leftX.Final, width: layout.finalWidth },
    { key: 'right-sf', label: '半决赛', x: layout.rightX.SF, width: layout.cardWidth },
    { key: 'right-qf', label: '四分之一决赛', x: layout.rightX.QF, width: layout.cardWidth },
    { key: 'right-r16', label: '16 强赛', x: layout.rightX.R16, width: layout.cardWidth },
    { key: 'right-r32', label: '32 强赛', x: layout.rightX.R32, width: layout.cardWidth },
  ];
}

function splitStats(stats: WorldCupPlayerStat[]): Record<StatTab, WorldCupPlayerStat[]> {
  const cleaned = stats.filter((stat) => stat.value != null && stat.title && stat.title !== '球员');
  const byCategory = (category: string) => cleaned.filter((stat) => stat.category === category);
  const goals = normalizeStatRows(byCategory('进球数'));
  const assists = normalizeStatRows(byCategory('助攻'));
  const yellow = normalizeStatRows(byCategory('黄牌'));
  const red = normalizeStatRows(byCategory('红牌'));
  const fallback = normalizeStatRows(cleaned);
  return {
    goals: goals.length ? goals : fallback.slice(0, 20),
    assists: assists.length ? assists : fallback.slice(20, 40),
    yellow: yellow.length ? yellow : fallback.slice(40, 60),
    red: red.length ? red : fallback.slice(60, 80),
  };
}

function normalizeStatRows(rows: WorldCupPlayerStat[]) {
  const bestByPlayer = new Map<string, WorldCupPlayerStat>();
  for (const row of rows) {
    const key = `${playerName(row).toLocaleLowerCase()}|${playerTeam(row).toLocaleLowerCase()}`;
    const existing = bestByPlayer.get(key);
    if (!existing || Number(row.value ?? 0) > Number(existing.value ?? 0)) {
      bestByPlayer.set(key, row);
    }
  }
  return [...bestByPlayer.values()].sort((a, b) => Number(b.value ?? 0) - Number(a.value ?? 0));
}

function playerName(stat: WorldCupPlayerStat) {
  if (stat.player_name) return stat.player_name;
  const value = stat.value == null ? '' : String(stat.value);
  const text = (stat.content || stat.title || '').replace(value, '').trim();
  const team = playerTeam(stat);
  return team ? text.replace(team, '').trim() : text;
}

function playerTeam(stat: WorldCupPlayerStat) {
  if (stat.team_name) return stat.team_name;
  const text = stat.content || stat.title || '';
  const known = Object.keys(TEAM_FLAG_CODE_BY_NAME).find((name) => text.includes(name));
  return known ?? '';
}

function displayTeamName(name: string) {
  return TEAM_DISPLAY_NAME[name] ?? name;
}

function teamNameTextSize(name: string) {
  return displayTeamName(name).length >= 7 ? 'text-[12px]' : 'text-sm';
}

function groupBy<T>(rows: T[], keyFn: (row: T) => string) {
  return rows.reduce<Record<string, T[]>>((acc, row) => {
    const key = keyFn(row);
    acc[key] = acc[key] ?? [];
    acc[key].push(row);
    return acc;
  }, {});
}

function matchLabel(match: WorldCupMatch) {
  if (match.stage === 'group') return match.group_name ? `${match.group_name} 组` : '小组赛';
  return roundName(match.stage);
}

function roundName(stage: string) {
  return {
    group: '小组赛',
    R32: '32 强赛',
    R16: '16 强赛',
    QF: '四分之一决赛',
    SF: '半决赛',
    ThirdPlace: '季军赛',
    Final: '决赛',
  }[stage] ?? stage;
}

function filterHistoryMatchesBySide(rows: WorldCupHistoryMatch[], homeQuery: string, awayQuery: string) {
  const home = normalizeHistoryTeamQuery(homeQuery);
  const away = normalizeHistoryTeamQuery(awayQuery);
  if (!home && !away) return rows;
  const exactPair = Boolean(home && away);
  return rows.filter((match) => {
    const homeNames = historyTeamSearchNames(match.home_team, match.home_team_zh);
    const awayNames = historyTeamSearchNames(match.away_team, match.away_team_zh);
    if (exactPair) return teamSearchExact(homeNames, home) && teamSearchExact(awayNames, away);
    if (home && !teamSearchFuzzy(homeNames, home)) return false;
    if (away && !teamSearchFuzzy(awayNames, away)) return false;
    return true;
  });
}

function historyTeamSearchNames(name: string | null | undefined, zh?: string | null) {
  return [name, zh, name ? historyTeamName(name, zh) : ''].filter(Boolean).map((item) => normalizeHistoryTeamQuery(String(item)));
}

function teamSearchFuzzy(names: string[], query: string) {
  return names.some((name) => name.includes(query));
}

function teamSearchExact(names: string[], query: string) {
  return names.some((name) => name === query);
}

function normalizeHistoryTeamQuery(value: string) {
  return value.trim().toLocaleLowerCase();
}

function historyTeamName(name: string | null | undefined, zh?: string | null) {
  return zh || name || '待定';
}

function historyHostNames(edition: WorldCupHistoryEdition) {
  return edition.host_countries_zh?.length ? edition.host_countries_zh : edition.host_countries;
}

function historyStageName(match: WorldCupHistoryMatch) {
  if (match.stage_zh) return match.stage_zh;
  if (match.stage === 'group') return match.round?.includes('Matchday') ? '小组赛' : (match.round ?? '小组赛');
  return roundName(match.stage);
}

function historyVenue(match: WorldCupHistoryMatch) {
  const venue = match.venue_zh ?? match.venue;
  const city = match.city_zh ?? match.city;
  return [venue, city].filter(Boolean).join('，') || '-';
}

function historyScore(match: WorldCupHistoryMatch) {
  if (match.home_score == null || match.away_score == null) return '-';
  const base = `${match.home_score}-${match.away_score}`;
  const extra = match.home_score_et == null || match.away_score_et == null
    ? ''
    : ` 加时 ${match.home_score_et}-${match.away_score_et}`;
  const penalty = match.home_penalty == null || match.away_penalty == null
    ? ''
    : ` 点球 ${match.home_penalty}-${match.away_penalty}`;
  return `${base}${extra}${penalty}`;
}

function shortMatchId(matchId: string) {
  return matchId.replace('SportRadar_Soccer_InternationalWorldCup_2026_Game_', 'W');
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return value;
  }
}

function defaultAgentContext(activeTab: TabKey): AgentPageContext {
  return {
    currentPage: 'worldcup-dashboard',
    activeTab,
    summary: `当前页面：${TABS.find((tab) => tab.key === activeTab)?.label ?? activeTab}`,
    data: { scope: 'page', tab: activeTab },
  };
}

function pageSessionKey(activeTab: TabKey) {
  return `page:${activeTab}`;
}

function sessionKeyForContext(context: AgentPageContext) {
  return context.currentMatchId ? `match:${context.currentMatchId}` : pageSessionKey((context.activeTab as TabKey | undefined) ?? 'matches');
}

function pageAgentContextForTab(
  activeTab: TabKey,
  data: {
    matches: WorldCupMatch[];
    bracket: WorldCupMatch[];
    standings: WorldCupStanding[];
    stats: WorldCupPlayerStat[];
    historyEditions: WorldCupHistoryEdition[];
    historyFinals: WorldCupHistoryMatch[];
    historyMatches: WorldCupHistoryMatch[];
    historyMode: HistoryViewMode;
    historyYear: number;
  },
): AgentPageContext {
  const base = defaultAgentContext(activeTab);
  if (activeTab === 'matches') {
    const complete = data.matches.filter((match) => match.status === 'complete').length;
    const scheduled = data.matches.filter((match) => match.status === 'scheduled').length;
    return {
      ...base,
      summary: `比赛页：${data.matches.length} 场，已赛 ${complete}，未赛 ${scheduled}`,
      data: {
        scope: 'page',
        tab: activeTab,
        totalMatches: data.matches.length,
        completeMatches: complete,
        scheduledMatches: scheduled,
        sampleMatches: data.matches.slice(0, 8).map(compactMatchForAgent),
      },
    };
  }
  if (activeTab === 'bracket') {
    const placeholderCount = data.bracket.filter(hasPlaceholderTeam).length;
    const currentContenders = currentBracketContenders(data.bracket);
    const eliminatedTeams = eliminatedBracketTeams(data.bracket, currentContenders);
    return {
      ...base,
      summary: `赛程表页：${data.bracket.length} 场淘汰赛，当前仍存活 ${currentContenders.length} 队，${placeholderCount} 场含占位路径`,
      data: {
        scope: 'page',
        tab: activeTab,
        totalMatches: data.bracket.length,
        placeholderMatches: placeholderCount,
        currentContenders,
        eliminatedTeams,
        currentRoundMatches: currentRoundMatches(data.bracket).map(compactMatchForAgent),
        sampleMatches: data.bracket.slice(0, 12).map(compactMatchForAgent),
      },
    };
  }
  if (activeTab === 'standings') {
    return {
      ...base,
      summary: `排名页：${data.standings.length} 条小组排名记录`,
      data: {
        scope: 'page',
        tab: activeTab,
        totalStandings: data.standings.length,
        sampleStandings: data.standings.slice(0, 12).map((row) => ({
          group: row.group_name,
          team: displayTeamName(row.team_name_raw),
          points: row.points,
          played: row.played,
          goalDifference: row.goal_difference,
        })),
      },
    };
  }
  if (activeTab === 'stats') {
    return {
      ...base,
      summary: `统计信息页：${data.stats.length} 条球员统计`,
      data: {
        scope: 'page',
        tab: activeTab,
        totalStats: data.stats.length,
        sampleStats: data.stats.slice(0, 12).map((row) => ({
          title: row.title,
          category: row.category,
          value: row.value,
          team: row.team_name,
        })),
      },
    };
  }
  return {
    ...base,
    summary: `历史世界杯页：${data.historyEditions.length} 届赛事，当前 ${data.historyYear}，模式 ${data.historyMode}`,
    data: {
      scope: 'page',
      tab: activeTab,
      historyMode: data.historyMode,
      selectedYear: data.historyYear,
      editionCount: data.historyEditions.length,
      finalsCount: data.historyFinals.length,
      loadedMatchCount: data.historyMatches.length,
      sampleFinals: data.historyFinals.slice(0, 8).map((match) => ({
        year: match.year,
        home: historyTeamName(match.home_team, match.home_team_zh),
        away: historyTeamName(match.away_team, match.away_team_zh),
        score: historyScore(match),
      })),
    },
  };
}

function compactMatchForAgent(match: WorldCupMatch) {
  return {
    matchId: shortMatchId(match.match_id),
    stage: match.stage,
    status: match.status,
    kickoff: match.kickoff_label || match.kickoff_time,
    home: displayTeamName(match.home_team_raw ?? match.home_team_id ?? '待定'),
    away: displayTeamName(match.away_team_raw ?? match.away_team_id ?? '待定'),
    score: match.home_score == null || match.away_score == null ? null : `${match.home_score}-${match.away_score}`,
    nextMatchId: match.next_match_id ? shortMatchId(match.next_match_id) : null,
    hasPlaceholder: hasPlaceholderTeam(match),
  };
}

function currentRoundMatches(matches: WorldCupMatch[]) {
  const stageOrder = ['Final', 'SF', 'QF', 'R16', 'R32'];
  for (const stage of stageOrder) {
    const rows = sortMatches(matches.filter((match) => match.stage === stage && match.status !== 'complete' && match.status !== 'final'));
    if (rows.length > 0) return rows;
  }
  for (const stage of stageOrder) {
    const rows = sortMatches(matches.filter((match) => match.stage === stage));
    if (rows.length > 0) return rows;
  }
  return [];
}

function currentBracketContenders(matches: WorldCupMatch[]) {
  return uniqueStrings(currentRoundMatches(matches).flatMap(matchConcreteTeams));
}

function eliminatedBracketTeams(matches: WorldCupMatch[], contenders: string[]) {
  const contenderSet = new Set(contenders);
  return uniqueStrings(
    matches
      .filter((match) => match.status === 'complete' || match.status === 'final')
      .flatMap(matchConcreteTeams)
      .filter((team) => !contenderSet.has(team)),
  );
}

function matchConcreteTeams(match: WorldCupMatch) {
  return [
    concreteTeamName(match.home_team_raw, match.home_team_id),
    concreteTeamName(match.away_team_raw, match.away_team_id),
  ].filter(Boolean) as string[];
}

function concreteTeamName(raw?: string | null, id?: string | null) {
  const value = raw || id || '';
  if (!value || /^[WL]\d{2,3}$/i.test(value)) return '';
  return displayTeamName(value);
}

function uniqueStrings(values: string[]) {
  return [...new Set(values.filter(Boolean))];
}

function matchAnalysisPrompt(match: WorldCupMatch) {
  if (hasPlaceholderTeam(match)) {
    return '请联网检索后做这场淘汰赛的路径情景推演和赛前预测：先说明 W/L 占位来源，再按可能晋级路径分析胜负倾向、关键变量和不确定性，不要把占位符当成确定球队。';
  }
  if (match.status !== 'complete' && match.status !== 'final') {
    return '请联网检索后做这场未赛比赛的赛前预测：给出胜负倾向、可能比分、关键变量、风险和需要确认的信息。';
  }
  return '请分析这场比赛。';
}

function hasPlaceholderTeam(match: WorldCupMatch) {
  return [match.home_team_id, match.away_team_id, match.home_team_raw, match.away_team_raw]
    .some((value) => /^[WL]\d{2,3}$/i.test(String(value ?? '').trim()));
}

function matchAgentContext(match: WorldCupMatch, activeTab: TabKey): AgentPageContext {
  const home = displayTeamName(match.home_team_raw ?? match.home_team_id ?? '待定');
  const away = displayTeamName(match.away_team_raw ?? match.away_team_id ?? '待定');
  return {
    currentPage: 'worldcup-dashboard',
    activeTab,
    currentMatchId: match.match_id,
    selectedDate: displayDateKey(match),
    summary: `${home} vs ${away} · ${matchLabel(match)} · ${formatMatchTime(match) || '时间待定'}`,
    data: {
      matchLabel: `${home} vs ${away}`,
      homeTeam: home,
      awayTeam: away,
      home_team_raw: home,
      away_team_raw: away,
      groupName: match.group_name,
      stage: match.stage,
      status: match.status,
      kickoffLabel: match.kickoff_label,
      score: match.home_score == null || match.away_score == null ? null : `${match.home_score}-${match.away_score}`,
    },
  };
}

function flagUrlForTeam(teamId?: string | null, teamName?: string | null, flagCode?: string | null) {
  const code = flagCode || (
    teamId && !/^[WL]\d+$/.test(teamId)
      ? TEAM_FLAG_CODE_BY_ID[teamId]
      : undefined
  );
  const resolvedCode = code ?? (teamName ? TEAM_FLAG_CODE_BY_NAME[teamName] : undefined);
  if (!resolvedCode) return '';
  return `https://flagcdn.com/w40/${resolvedCode}.png`;
}

const TEAM_FLAG_CODE_BY_ID: Record<string, string> = {
  ALG: 'dz', ARG: 'ar', AUS: 'au', AUT: 'at', BEL: 'be', BIH: 'ba', BRA: 'br',
  CAN: 'ca', CIV: 'ci', COD: 'cd', COL: 'co', CPV: 'cv', CRO: 'hr', CUW: 'cw',
  CZE: 'cz', ECU: 'ec', EGY: 'eg', ENG: 'gb-eng', ESP: 'es', FRA: 'fr', GER: 'de',
  GHA: 'gh', HAI: 'ht', IRN: 'ir', IRQ: 'iq', JOR: 'jo', JPN: 'jp', KOR: 'kr',
  KSA: 'sa', MAR: 'ma', MEX: 'mx', NED: 'nl', NOR: 'no', NZL: 'nz', PAN: 'pa',
  PAR: 'py', POR: 'pt', QAT: 'qa', RSA: 'za', SCO: 'gb-sct', SEN: 'sn',
  SUI: 'ch', SWE: 'se', TUN: 'tn', TUR: 'tr', URU: 'uy', USA: 'us', UZB: 'uz',
};

const TEAM_FLAG_CODE_BY_NAME: Record<string, string> = {
  阿尔及利亚: 'dz', 阿根廷: 'ar', 澳大利亚: 'au', 奥地利: 'at', 比利时: 'be',
  波黑: 'ba', 巴西: 'br', 加拿大: 'ca', 科特迪瓦: 'ci', 刚果民主共和国: 'cd',
  哥伦比亚: 'co', 佛得角: 'cv', 克罗地亚: 'hr', 库拉索岛: 'cw', 捷克: 'cz',
  厄瓜多尔: 'ec', 埃及: 'eg', 英格兰: 'gb-eng', 西班牙: 'es', 法国: 'fr',
  德国: 'de', 加纳: 'gh', 海地: 'ht', 伊朗: 'ir', 伊拉克: 'iq',
  约旦: 'jo', 日本: 'jp', 韩国: 'kr', 沙特阿拉伯: 'sa', 摩洛哥: 'ma',
  墨西哥: 'mx', 荷兰: 'nl', 挪威: 'no', 新西兰: 'nz', 巴拿马: 'pa',
  巴拉圭: 'py', 葡萄牙: 'pt', 卡塔尔: 'qa', 南非: 'za', 苏格兰: 'gb-sct',
  塞内加尔: 'sn', 瑞士: 'ch', 瑞典: 'se', 突尼斯: 'tn', 土耳其: 'tr',
  乌拉圭: 'uy', 美国: 'us', 乌兹别克斯坦: 'uz',
};

const TEAM_DISPLAY_NAME: Record<string, string> = {
  象牙海岸: '科特迪瓦',
};

export default App;
