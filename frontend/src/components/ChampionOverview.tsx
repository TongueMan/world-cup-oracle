import type { TournamentPrediction } from '../lib/types';
import { getTeamName } from '../lib/constants';

interface ChampionOverviewProps {
  prediction: TournamentPrediction;
}

interface ChampionCardData {
  label: string;
  teamId: string | null;
  accentClass: string;
  icon: string;
}

export function ChampionOverview({ prediction }: ChampionOverviewProps) {
  const cards: ChampionCardData[] = [
    {
      label: '综合冠军',
      teamId: prediction.champion_team_id,
      accentClass: 'border-amber-400 bg-amber-50',
      icon: '🏆',
    },
    {
      label: '理性冠军',
      teamId: prediction.rational_champion,
      accentClass: 'border-blue-400 bg-blue-50',
      icon: '📊',
    },
    {
      label: '叙事冠军',
      teamId: prediction.narrative_champion,
      accentClass: 'border-purple-400 bg-purple-50',
      icon: '📖',
    },
    {
      label: '象征冠军',
      teamId: prediction.symbolic_champion,
      accentClass: 'border-teal-400 bg-teal-50',
      icon: '🔮',
    },
  ];

  const runnerUp = prediction.runner_up_team_id;
  const semifinalists = prediction.semifinalists;

  return (
    <section>
      <h2 className="mb-4 text-xl font-bold text-slate-800">冠军预言</h2>

      {/* 四张冠军卡片 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((card) => {
          const teamName = getTeamName(card.teamId);
          const isPending = !card.teamId;
          return (
            <div
              key={card.label}
              className={`rounded-xl border-2 p-4 text-center ${card.accentClass}`}
            >
              <div className="mb-1 text-2xl">{card.icon}</div>
              <div className="text-xs font-medium text-slate-500">{card.label}</div>
              <div
                className={`mt-1 text-lg font-bold ${
                  isPending ? 'text-slate-400' : 'text-slate-800'
                }`}
              >
                {teamName}
              </div>
              {card.teamId && (
                <div className="text-xs text-slate-400">{card.teamId}</div>
              )}
            </div>
          );
        })}
      </div>

      {/* 亚军和四强 */}
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2 rounded-lg bg-slate-100 px-4 py-2">
          <span className="text-sm text-slate-500">🥈 亚军</span>
          <span className="font-bold text-slate-700">
            {getTeamName(runnerUp)}
          </span>
          {runnerUp && (
            <span className="text-xs text-slate-400">{runnerUp}</span>
          )}
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-slate-100 px-4 py-2">
          <span className="text-sm text-slate-500">🎯 四强</span>
          <div className="flex flex-wrap gap-1.5">
            {semifinalists.length > 0 ? (
              semifinalists.map((id) => (
                <span
                  key={id}
                  className="rounded-md bg-white px-2 py-0.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200"
                >
                  {getTeamName(id)}
                </span>
              ))
            ) : (
              <span className="text-sm text-slate-400">待定</span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
