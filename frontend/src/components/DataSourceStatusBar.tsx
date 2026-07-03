import type { DataSourceStatus } from '../lib/types';

interface DataSourceStatusBarProps {
  sources: DataSourceStatus[];
  notes: string[];
}

export function DataSourceStatusBar({ sources, notes }: DataSourceStatusBarProps) {
  return (
    <section className="oracle-panel p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-white">数据源状态</h2>
        <span className="text-xs text-slate-500">FIFA 主源 · 可信源补齐 · 无兜底</span>
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {sources.map((source) => (
          <div key={source.source_key} className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-100">{source.source_key}</span>
              <span className={statusClass(source.status)}>{source.status}</span>
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">{source.message}</p>
          </div>
        ))}
      </div>
      {notes.length > 0 && (
        <div className="mt-3 rounded-xl border border-[#cdb36b]/25 bg-[#cdb36b]/10 p-3 text-sm text-[#f2dd9a]">
          {notes[0]}
        </div>
      )}
    </section>
  );
}

function statusClass(status: string): string {
  if (status === 'ok') return 'rounded-full bg-emerald-300/15 px-2 py-0.5 text-xs text-emerald-100';
  if (status === 'error') return 'rounded-full bg-rose-300/15 px-2 py-0.5 text-xs text-rose-100';
  return 'rounded-full bg-slate-200/10 px-2 py-0.5 text-xs text-slate-300';
}
