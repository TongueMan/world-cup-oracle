import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { MatchDetail, MatchPrediction } from '../lib/types';
import { getTeamName } from '../lib/constants';

interface MatchDetailDrawerProps {
  prediction: MatchPrediction | null;
  matchId: string | null;
  onClose: () => void;
}

interface ProbBarProps {
  label: string;
  value: number;
  color: string;
}

function ProbBar({ label, value, color }: ProbBarProps) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 shrink-0 text-xs text-slate-500">{label}</span>
      <div className="h-4 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right text-xs font-medium text-slate-700">
        {pct}%
      </span>
    </div>
  );
}

export function MatchDetailDrawer({
  prediction,
  matchId,
  onClose,
}: MatchDetailDrawerProps) {
  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!matchId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    api
      .getMatch(matchId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled && prediction) {
          setDetail({
            prediction,
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [matchId, prediction]);

  if (!matchId) return null;

  const activePrediction = detail?.prediction ?? prediction;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center"
      onClick={onClose}
    >
      <div
        className="max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900">单场推演</h3>
            <p className="text-xs text-slate-400">{matchId}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100"
          >
            关闭
          </button>
        </div>

        {loading && !activePrediction && (
          <div className="py-10 text-center text-sm text-slate-400">加载中...</div>
        )}

        {activePrediction && (
          <div className="space-y-5">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">
                    {getTeamName(activePrediction.home_team_id)} vs{' '}
                    {getTeamName(activePrediction.away_team_id)}
                  </div>
                  <div className="mt-1 text-3xl font-bold text-slate-900">
                    {activePrediction.predicted_score}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-slate-400">预测胜者</div>
                  <div className="text-xl font-bold text-emerald-700">
                    {getTeamName(activePrediction.winner_team_id)}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
              <div className="space-y-2">
                <ProbBar label="主胜" value={activePrediction.home_win_prob} color="bg-emerald-500" />
                <ProbBar label="平局" value={activePrediction.draw_prob} color="bg-amber-500" />
                <ProbBar label="客胜" value={activePrediction.away_win_prob} color="bg-rose-500" />
              </div>
              <div className="grid grid-cols-3 gap-2 text-center lg:grid-cols-1">
                <Metric label="置信度" value={`${Math.round(activePrediction.confidence * 100)}%`} />
                <Metric label="爆冷" value={activePrediction.upset_index.toFixed(2)} />
                <Metric label="点球" value={`${Math.round(activePrediction.penalty_prob * 100)}%`} />
              </div>
            </div>

            <TextPanel title="战术分析" text={activePrediction.tactical_summary} />
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-1 font-bold text-slate-800">{value}</div>
    </div>
  );
}

function TextPanel({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-xs font-medium text-slate-400">{title}</div>
      <p className="mt-1 text-sm leading-6 text-slate-700">{text || '暂无结构化信号'}</p>
    </div>
  );
}
