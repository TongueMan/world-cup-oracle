import { useState } from 'react';
import type { DataQualityReport, TournamentPrediction } from '../lib/types';
import { PREDICTION_MODES } from '../lib/constants';

interface ControlBarProps {
  onRunPrediction: (seed: number, mode: string) => void;
  loading: boolean;
  prediction?: TournamentPrediction | null;
  dataStatus?: DataQualityReport | null;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '等待 Bing 知识库快照';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function statusTone(status?: string) {
  if (status === 'ready') return 'border-emerald-200/50 bg-emerald-300/15 text-emerald-50';
  if (status === 'data_unavailable' || status === 'invalid') {
    return 'border-amber-200/45 bg-amber-300/14 text-amber-50';
  }
  return 'border-white/25 bg-white/10 text-white/80';
}

export function ControlBar({
  onRunPrediction,
  loading,
  prediction,
  dataStatus,
}: ControlBarProps) {
  const [seed, setSeed] = useState(42);
  const [mode, setMode] = useState('balanced');
  const statusLabel =
    dataStatus?.status === 'ready'
      ? '知识库就绪'
      : dataStatus?.status === 'data_unavailable'
        ? '等待 Bing 数据'
        : dataStatus?.status === 'invalid'
          ? '字段不足'
          : '待同步';

  return (
    <header className="relative border-b border-white/12 bg-[#061208]/80 shadow-[0_18px_50px_rgba(0,0,0,0.35)] backdrop-blur-xl">
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center gap-4">
            <div className="football-icon" aria-hidden="true" />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-black tracking-wide text-white sm:text-2xl">
                  World Cup Oracle
                </h1>
                <span className={`rounded-full border px-2.5 py-1 text-xs ${statusTone(dataStatus?.status)}`}>
                  {statusLabel}
                </span>
              </div>
              <p className="mt-1 text-sm text-white/58">
                世界杯冠军预测指挥舱 · Bing Sports 单源知识库 · 最近更新 {formatTime(prediction?.generated_at)}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/15 bg-black/24 p-2 backdrop-blur">
            <label className="flex items-center gap-2 rounded-xl border border-white/12 bg-white/8 px-3 py-2 text-sm text-white/72">
              <span className="text-xs uppercase tracking-[0.2em] text-[#ffe18a]">Seed</span>
              <input
                type="number"
                value={seed}
                min={0}
                max={999999}
                onChange={(event) => setSeed(Number(event.target.value) || 0)}
                className="w-20 bg-transparent text-right font-semibold text-white outline-none"
              />
            </label>

            <label className="flex items-center gap-2 rounded-xl border border-white/12 bg-white/8 px-3 py-2 text-sm text-white/72">
              <span className="text-xs uppercase tracking-[0.2em] text-[#ffe18a]">Mode</span>
              <select
                value={mode}
                onChange={(event) => setMode(event.target.value)}
                className="bg-transparent font-semibold text-white outline-none"
              >
                {PREDICTION_MODES.map((item) => (
                  <option key={item.value} value={item.value} className="bg-[#0f2716] text-white">
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={() => onRunPrediction(seed, mode)}
              disabled={loading}
              className="rounded-xl bg-[#f6c845] px-4 py-2 text-sm font-black text-[#13210b] shadow-[0_0_28px_rgba(246,200,69,0.24)] transition hover:bg-[#ffe18a] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? '同步中' : '同步 Bing 知识库'}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
