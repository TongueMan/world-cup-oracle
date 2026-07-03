import { useState, useMemo } from 'react';
import type { Bracket, KnockoutSlot, MatchPrediction } from '../lib/types';
import { getTeamName, getRoundLabel } from '../lib/constants';
import { MatchDetailDrawer } from './MatchDetailDrawer';

interface KnockoutBracketProps {
  bracket: Bracket;
  matchPredictions?: MatchPrediction[];
}

const ROUND_ORDER = ['R32', 'R16', 'QF', 'SF', 'Final'];

function roundPriority(round: string): number {
  const idx = ROUND_ORDER.indexOf(round);
  return idx >= 0 ? idx : ROUND_ORDER.length;
}

interface SlotProps {
  slot: KnockoutSlot;
  onClick: () => void;
}

function SlotCard({ slot, onClick }: SlotProps) {
  const homeWin = slot.winner_team_id === slot.home_team_id;
  const awayWin = slot.winner_team_id === slot.away_team_id;
  const hasScore = slot.home_score !== null && slot.away_score !== null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-56 shrink-0 rounded-lg border border-slate-200 bg-white p-0 text-left shadow-sm transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-emerald-400"
    >
      {/* 主队 */}
      <div
        className={`flex items-center justify-between px-3 py-2 ${
          homeWin ? 'bg-emerald-50 font-bold' : ''
        }`}
      >
        <span className="flex items-center gap-1.5 text-sm text-slate-700">
          {homeWin && <span className="text-emerald-600">▶</span>}
          <span className="text-xs text-slate-400">{slot.home_team_id ?? '—'}</span>
          <span className={homeWin ? 'text-slate-800' : 'text-slate-600'}>
            {getTeamName(slot.home_team_id)}
          </span>
        </span>
        <span className={`text-sm font-bold ${homeWin ? 'text-emerald-700' : 'text-slate-500'}`}>
          {hasScore ? slot.home_score : '—'}
        </span>
      </div>

      <div className="border-t border-slate-100" />

      {/* 客队 */}
      <div
        className={`flex items-center justify-between px-3 py-2 ${
          awayWin ? 'bg-emerald-50 font-bold' : ''
        }`}
      >
        <span className="flex items-center gap-1.5 text-sm text-slate-700">
          {awayWin && <span className="text-emerald-600">▶</span>}
          <span className="text-xs text-slate-400">{slot.away_team_id ?? '—'}</span>
          <span className={awayWin ? 'text-slate-800' : 'text-slate-600'}>
            {getTeamName(slot.away_team_id)}
          </span>
        </span>
        <span className={`text-sm font-bold ${awayWin ? 'text-emerald-700' : 'text-slate-500'}`}>
          {hasScore ? slot.away_score : '—'}
        </span>
      </div>

      {/* 点球提示 */}
      {slot.went_to_penalties && (
        <div className="border-t border-slate-100 bg-amber-50 px-3 py-1 text-center text-xs text-amber-600">
          点球大战
        </div>
      )}
    </button>
  );
}

export function KnockoutBracket({ bracket, matchPredictions }: KnockoutBracketProps) {
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);

  // match_id → MatchPrediction 映射
  const matchMap = useMemo(() => {
    const map = new Map<string, MatchPrediction>();
    if (matchPredictions) {
      for (const mp of matchPredictions) {
        map.set(mp.match_id, mp);
      }
    }
    return map;
  }, [matchPredictions]);

  // 按轮次分组
  const rounds = useMemo(() => {
    const grouped = new Map<string, KnockoutSlot[]>();
    for (const slot of bracket.slots) {
      const arr = grouped.get(slot.round) ?? [];
      arr.push(slot);
      grouped.set(slot.round, arr);
    }
    return Array.from(grouped.entries()).sort(
      (a, b) => roundPriority(a[0]) - roundPriority(b[0]),
    );
  }, [bracket.slots]);

  const champion = bracket.champion_team_id;
  const runnerUp = bracket.runner_up_team_id;
  const selectedPrediction = selectedMatchId ? matchMap.get(selectedMatchId) ?? null : null;

  return (
    <section>
      <h2 className="mb-4 text-xl font-bold text-slate-800">淘汰赛</h2>

      {/* 冠军与亚军展示 */}
      <div className="mb-4 flex flex-wrap gap-3">
        {champion && (
          <div className="flex items-center gap-2 rounded-xl border-2 border-amber-300 bg-amber-50 px-4 py-2">
            <span className="text-xl">🏆</span>
            <div>
              <div className="text-xs text-slate-500">冠军</div>
              <div className="font-bold text-slate-800">{getTeamName(champion)}</div>
              <div className="text-xs text-slate-400">{champion}</div>
            </div>
          </div>
        )}
        {runnerUp && (
          <div className="flex items-center gap-2 rounded-xl border-2 border-slate-300 bg-slate-50 px-4 py-2">
            <span className="text-xl">🥈</span>
            <div>
              <div className="text-xs text-slate-500">亚军</div>
              <div className="font-bold text-slate-700">{getTeamName(runnerUp)}</div>
              <div className="text-xs text-slate-400">{runnerUp}</div>
            </div>
          </div>
        )}
      </div>

      {/* 赛程树 — 横向滚动 */}
      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max gap-6">
          {rounds.map(([round, slots]) => (
            <div key={round} className="flex flex-col">
              <div className="mb-3 text-center text-sm font-semibold text-slate-600">
                {getRoundLabel(round)}
              </div>
              <div className="flex flex-1 flex-col justify-around gap-4">
                {slots.map((slot) => (
                  <SlotCard
                    key={slot.match_id}
                    slot={slot}
                    onClick={() => setSelectedMatchId(slot.match_id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 比赛详情抽屉 */}
      <MatchDetailDrawer
        prediction={selectedPrediction}
        matchId={selectedMatchId}
        onClose={() => setSelectedMatchId(null)}
      />
    </section>
  );
}
