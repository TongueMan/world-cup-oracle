import type { ReactNode } from 'react';
import type { TournamentPrediction } from '../lib/types';
import { getTeamName } from '../lib/constants';

interface CommandInsightsProps {
  prediction: TournamentPrediction;
}

export function CommandInsights({ prediction }: CommandInsightsProps) {
  const probabilities = prediction.champion_probabilities.slice(0, 8);

  return (
    <section>
      <Panel title="冠军概率榜">
        <div className="space-y-2">
          {probabilities.map((item) => (
            <RankRow
              key={item.team_id}
              label={getTeamName(item.team_id)}
              value={`${Math.round(item.probability * 100)}%`}
              width={item.probability}
            />
          ))}
        </div>
      </Panel>
    </section>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-3 font-semibold text-slate-800">{title}</h3>
      {children}
    </div>
  );
}

function RankRow({
  label,
  value,
  width,
}: {
  label: string;
  value: string;
  width: number;
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-medium text-slate-600">{label}</span>
        <span className="text-slate-400">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${Math.max(5, Math.min(100, width * 100))}%` }}
        />
      </div>
    </div>
  );
}
