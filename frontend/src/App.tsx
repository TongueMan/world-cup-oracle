import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './lib/api';
import type {
  WorldCupMatch,
  WorldCupPlayerStat,
  WorldCupStanding,
  WorldCupSyncStatus,
} from './lib/types';

type TabKey = 'matches' | 'bracket' | 'standings' | 'stats';
type StatTab = 'goals' | 'assists' | 'yellow' | 'red';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'matches', label: '比赛' },
  { key: 'bracket', label: '赛程表' },
  { key: 'standings', label: '排名' },
  { key: 'stats', label: '统计信息' },
];

const STAT_TABS: Array<{ key: StatTab; label: string }> = [
  { key: 'goals', label: '进球数' },
  { key: 'assists', label: '助攻' },
  { key: 'yellow', label: '黄牌' },
  { key: 'red', label: '红牌' },
];

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('matches');
  const [matches, setMatches] = useState<WorldCupMatch[]>([]);
  const [bracket, setBracket] = useState<WorldCupMatch[]>([]);
  const [standings, setStandings] = useState<WorldCupStanding[]>([]);
  const [stats, setStats] = useState<WorldCupPlayerStat[]>([]);
  const [syncStatus, setSyncStatus] = useState<WorldCupSyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [status, matchRows, bracketRows, standingRows, statRows] = await Promise.all([
        api.getWorldCupSyncStatus(),
        api.getWorldCupMatches(),
        api.getWorldCupBracket(),
        api.getWorldCupStandings(),
        api.getWorldCupPlayerStats(),
      ]);
      setSyncStatus(status);
      setMatches(sortMatches(matchRows));
      setBracket(sortMatches(bracketRows));
      setStandings(standingRows);
      setStats(statRows);
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

  useEffect(() => {
    void loadData();
  }, []);

  const completeCount = matches.filter((match) => match.status === 'complete').length;
  const scheduledCount = matches.filter((match) => match.status === 'scheduled').length;
  const statusText = syncStatus?.last_status === 'success' ? '已更新' : syncStatus?.last_status === 'partial' ? '部分更新' : '待更新';

  return (
    <div className="min-h-screen bg-[#07140b] text-white">
      <div className="stadium-backdrop" />
      <header className="sticky top-0 z-50 border-b border-white/12 bg-[#061208]/92 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="flex items-center gap-4">
            <div className="football-icon" aria-hidden="true" />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-black tracking-wide">世界杯冠军预测智能体</h1>
                <span className="rounded-full border border-emerald-200/35 bg-emerald-300/14 px-3 py-1 text-xs font-bold text-emerald-50">
                  {statusText}
                </span>
              </div>
              <p className="mt-1 text-sm text-white/58">
                数据来源：Bing 体育 · 最近更新：{formatDateTime(syncStatus?.last_success_at) || '暂无'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleSync}
            disabled={syncing}
            className="rounded-xl bg-[#f6c845] px-4 py-2 text-sm font-black text-[#13210b] shadow-[0_0_28px_rgba(246,200,69,0.24)] transition hover:bg-[#ffe18a] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {syncing ? '更新中' : '更新赛程数据'}
          </button>
        </div>
      </header>

      <main className="relative mx-auto max-w-7xl space-y-6 px-4 pb-8 pt-5 sm:px-6 lg:px-8">
        <section className="hero-field overflow-hidden rounded-[28px] border border-white/15">
          <div className="grid gap-6 p-5 sm:p-7 lg:grid-cols-[1.05fr_0.95fr] lg:p-8">
            <div>
              <p className="text-xs font-semibold tracking-[0.24em] text-[#ffe18a]">
                2026 世界杯实时赛程
              </p>
              <h2 className="mt-4 max-w-3xl text-4xl font-black leading-tight text-white sm:text-5xl">
                世界杯赛程与赛果指挥舱
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-white/78">
                集中查看比赛结果、淘汰赛赛程、小组排名和球员统计。已完赛显示比分和点球，未赛显示开球时间。
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

        {error && (
          <div className="rounded-2xl border border-rose-200/30 bg-rose-500/12 p-4 text-sm text-rose-50">
            {error}
          </div>
        )}

        <section className={`oracle-panel p-4 sm:p-5 ${activeTab === 'bracket' ? 'oracle-panel-wide' : ''}`}>
          <div className="sticky top-[92px] z-30 -mx-4 mb-5 flex flex-wrap gap-2 border-b border-white/10 bg-[#08210f]/92 px-4 py-3 backdrop-blur sm:-mx-5 sm:px-5">
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

          {loading ? (
            <div className="flex min-h-64 items-center justify-center">
              <div className="football-spinner" />
            </div>
          ) : (
            <>
              {activeTab === 'matches' && <MatchesView matches={matches} />}
              {activeTab === 'bracket' && <BracketView matches={bracket} />}
              {activeTab === 'standings' && <StandingsView standings={standings} />}
              {activeTab === 'stats' && <StatsView stats={stats} />}
            </>
          )}
        </section>
      </main>
    </div>
  );
}

function MatchesView({ matches }: { matches: WorldCupMatch[] }) {
  const groups = useMemo(() => groupMatchesByDate(matches), [matches]);
  const todayKey = useMemo(() => nearestMatchDateKey(groups), [groups]);
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    const target = todayKey ? sectionRefs.current[todayKey] : null;
    if (target) {
      target.scrollIntoView({ block: 'start' });
    }
  }, [todayKey]);

  return (
    <div className="space-y-7">
      {groups.map(([date, rows]) => (
        <div key={date} ref={(node) => { sectionRefs.current[date] = node; }}>
          <h3 className="mb-3 text-base font-black text-[#ffe18a]">{date}</h3>
          <div className="grid overflow-hidden rounded-3xl border border-white/10 bg-[#f4efea]/95 text-[#171c18] md:grid-cols-2">
            {rows.map((match) => (
              <MatchCard key={match.match_id} match={match} light />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function BracketView({ matches }: { matches: WorldCupMatch[] }) {
  const layout = buildBracketLayout(matches);
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
            <MatchCard match={card.match} light compact />
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
          <h3 className="mb-4 text-xl font-black">{group} 组</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead className="text-[#6d716b]">
                <tr>
                  <th className="py-2 text-left">球队</th>
                  <th>场次</th>
                  <th>胜</th>
                  <th>平</th>
                  <th>负场</th>
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
                    <td className="text-center">{row.played}</td>
                    <td className="text-center">{row.won}</td>
                    <td className="text-center">{row.drawn}</td>
                    <td className="text-center">{row.lost}</td>
                    <td className="text-center">{row.goals_for}</td>
                    <td className="text-center">{row.goals_against}</td>
                    <td className="text-center">{row.goal_difference}</td>
                    <td className="text-center font-black">{row.points}</td>
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

function MatchCard({ match, compact = false, light = false }: { match: WorldCupMatch; compact?: boolean; light?: boolean }) {
  const cardClass = light
    ? 'border-black/8 bg-[#f4efea] text-[#151a16]'
    : 'border-white/12 bg-[#08210f]/74 text-white';
  const sizingClass = compact ? 'h-[112px] overflow-hidden p-3' : 'p-4';
  return (
    <div className={`border ${sizingClass} ${cardClass}`}>
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

function FlagIcon({ teamId, teamName }: { teamId: string | null | undefined; teamName?: string | null }) {
  const src = flagUrlForTeam(teamId, teamName);
  if (!src) {
    return <span className="mr-2 inline-block h-4 w-6 rounded-sm border border-black/10 bg-slate-200 align-[-2px]" />;
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
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
  const base = new Date(2026, 6, 3);
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

function buildBracketLayout(matches: WorldCupMatch[]) {
  const width = 2520;
  const height = 1160;
  const cardWidth = 196;
  const finalWidth = 260;
  const cardHeight = 112;
  const leftX = {
    R32: 80,
    R16: 340,
    QF: 600,
    SF: 850,
    Final: 1050,
  };
  const rightX = {
    SF: 1420,
    QF: 1670,
    R16: 1930,
    R32: 2220,
  };
  const y = {
    R32: [78, 208, 338, 468, 598, 728, 858, 988],
    R16: [143, 403, 663, 923],
    QF: [273, 793],
    SF: [533],
    Final: [533],
  };
  const final = matches.find((match) => match.stage === 'Final');
  const childrenOf = (match: WorldCupMatch | undefined, stage?: string) => {
    if (!match) return [];
    return sortMatches(
      matches.filter((row) => row.next_match_id === match.match_id && (!stage || row.stage === stage)),
    );
  };

  const cards: BracketCardNode[] = [];
  const links: BracketConnector[] = [];

  const addCard = (key: string, match: WorldCupMatch, xPos: number, yPos: number, width = cardWidth) => {
    cards.push({ key, match, x: xPos, y: yPos, width });
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

  leftR32.forEach((match, index) => addCard(`left-r32-${match.match_id}`, match, leftX.R32, y.R32[index]));
  leftR16.forEach((match, index) => addCard(`left-r16-${match.match_id}`, match, leftX.R16, y.R16[index]));
  leftQF.forEach((match, index) => addCard(`left-qf-${match.match_id}`, match, leftX.QF, y.QF[index]));
  if (leftSF) addCard(`left-sf-${leftSF.match_id}`, leftSF, leftX.SF, y.SF[0]);
  if (final) addCard(`final-${final.match_id}`, final, leftX.Final, y.Final[0], finalWidth);
  if (rightSF) addCard(`right-sf-${rightSF.match_id}`, rightSF, rightX.SF, y.SF[0]);
  rightQF.forEach((match, index) => addCard(`right-qf-${match.match_id}`, match, rightX.QF, y.QF[index]));
  rightR16.forEach((match, index) => addCard(`right-r16-${match.match_id}`, match, rightX.R16, y.R16[index]));
  rightR32.forEach((match, index) => addCard(`right-r32-${match.match_id}`, match, rightX.R32, y.R32[index]));

  const centerOf = (yPos: number) => yPos + cardHeight / 2;
  const addLeftPairLinks = (fromX: number, fromYs: number[], toX: number, toYs: number[], key: string) => {
    for (let index = 0; index < toYs.length; index += 1) {
      const y1 = fromYs[index * 2];
      const y2 = fromYs[index * 2 + 1];
      const targetY = toYs[index];
      if (y1 == null || y2 == null || targetY == null) continue;
      const sourceX = fromX + cardWidth;
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
      const targetX = toX + cardWidth;
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

  addLeftPairLinks(leftX.R32, y.R32.slice(0, leftR32.length), leftX.R16, y.R16.slice(0, leftR16.length), 'left-r32-r16');
  addLeftPairLinks(leftX.R16, y.R16.slice(0, leftR16.length), leftX.QF, y.QF.slice(0, leftQF.length), 'left-r16-qf');
  addLeftPairLinks(leftX.QF, y.QF.slice(0, leftQF.length), leftX.SF, y.SF, 'left-qf-sf');
  if (leftSF && final) {
    links.push({
      key: 'left-sf-final',
      d: `M ${leftX.SF + cardWidth} ${centerOf(y.SF[0])} H ${leftX.Final}`,
    });
  }

  addRightPairLinks(rightX.R32, y.R32.slice(0, rightR32.length), rightX.R16, y.R16.slice(0, rightR16.length), 'right-r32-r16');
  addRightPairLinks(rightX.R16, y.R16.slice(0, rightR16.length), rightX.QF, y.QF.slice(0, rightQF.length), 'right-r16-qf');
  addRightPairLinks(rightX.QF, y.QF.slice(0, rightQF.length), rightX.SF, y.SF, 'right-qf-sf');
  if (rightSF && final) {
    links.push({
      key: 'right-sf-final',
      d: `M ${rightX.SF} ${centerOf(y.SF[0])} H ${leftX.Final + finalWidth}`,
    });
  }

  const headers: BracketHeaderNode[] = [
    { key: 'left-r32', label: '32 强赛', x: leftX.R32, width: cardWidth },
    { key: 'left-r16', label: '16 强赛', x: leftX.R16, width: cardWidth },
    { key: 'left-qf', label: '四分之一决赛', x: leftX.QF, width: cardWidth },
    { key: 'left-sf', label: '半决赛', x: leftX.SF, width: cardWidth },
    { key: 'final', label: '决赛', x: leftX.Final, width: finalWidth },
    { key: 'right-sf', label: '半决赛', x: rightX.SF, width: cardWidth },
    { key: 'right-qf', label: '四分之一决赛', x: rightX.QF, width: cardWidth },
    { key: 'right-r16', label: '16 强赛', x: rightX.R16, width: cardWidth },
    { key: 'right-r32', label: '32 强赛', x: rightX.R32, width: cardWidth },
  ];

  return {
    width,
    height,
    headers,
    cards,
    links,
  };
}

function splitStats(stats: WorldCupPlayerStat[]): Record<StatTab, WorldCupPlayerStat[]> {
  const cleaned = stats.filter((stat) => stat.value != null && stat.title && stat.title !== '球员');
  const byCategory = (category: string) => cleaned.filter((stat) => stat.category === category);
  const goals = byCategory('进球数');
  const assists = byCategory('助攻');
  const yellow = byCategory('黄牌');
  const red = byCategory('红牌');
  return {
    goals: goals.length ? goals : cleaned.slice(0, 20),
    assists: assists.length ? assists : cleaned.slice(20, 40),
    yellow: yellow.length ? yellow : cleaned.slice(40, 60),
    red: red.length ? red : cleaned.slice(60, 80),
  };
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

function flagUrlForTeam(teamId: string | null | undefined, teamName?: string | null) {
  const code = teamId && !/^[WL]\d+$/.test(teamId)
    ? TEAM_FLAG_CODE_BY_ID[teamId]
    : undefined;
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
  波黑: 'ba', 巴西: 'br', 加拿大: 'ca', 象牙海岸: 'ci', 刚果民主共和国: 'cd',
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
