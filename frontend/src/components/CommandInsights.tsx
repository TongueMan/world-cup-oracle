import type { ReactNode } from 'react';
import type { TournamentPrediction } from '../lib/types';
import { getTeamName } from '../lib/constants';

interface CommandInsightsProps {
  prediction: TournamentPrediction;
}

export function CommandInsights({ prediction }: CommandInsightsProps) {
  const probabilities = prediction.champion_probabilities.slice(0, 8);
  const darkHorses = prediction.dark_horses.slice(0, 5);
  const upsets = prediction.upset_alerts.slice(0, 5);

  return (
    <section className="grid gap-4 lg:grid-cols-3">
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
      <Panel title="黑马雷达">
        <div className="space-y-2">
          {darkHorses.map((item) => {
            const teamId = String(item.team_id ?? '');
            const score = Number(item.score ?? 0);
            return (
              <RankRow
                key={teamId}
                label={getTeamName(teamId)}
                value={score.toFixed(2)}
                width={score}
              />
            );
          })}
        </div>
      </Panel>
      <Panel title="爆冷预警">
        <div className="space-y-2">
          {upsets.map((item) => {
            const matchId = String(item.match_id ?? '');
            const score = Number(item.upset_index ?? 0);
            return (
              <RankRow key={matchId} label={matchId} value={score.toFixed(2)} width={score} />
            );
          })}
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
