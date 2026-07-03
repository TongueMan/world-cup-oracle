import type { DebateTranscript } from '../lib/types';
import { getTeamName } from '../lib/constants';

interface AgentDebateProps {
  transcripts?: DebateTranscript[];
}

export function AgentDebate({ transcripts = [] }: AgentDebateProps) {
  const featured = transcripts.slice(0, 3);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800">Agent 辩论席</h2>
        <span className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-500">
          {transcripts.length} 场已缓存
        </span>
      </div>

      {featured.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
          关键比赛的 Agent 辩论将在预测完成后生成，也可以在单场详情中按需生成。
        </div>
      ) : (
        <div className="space-y-4">
          {featured.map((transcript) => (
            <article key={transcript.match_id} className="rounded-lg bg-slate-50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="font-semibold text-slate-800">{transcript.match_id}</div>
                <div className="text-xs text-slate-500">
                  Judge: {getTeamName(transcript.judge_decision?.winner_team_id)}
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                {transcript.opinions.slice(0, 6).map((opinion) => (
                  <div key={opinion.agent} className="rounded-md bg-white p-3">
                    <div className="text-sm font-medium text-slate-700">{opinion.agent}</div>
                    <div className="mt-1 text-xs text-slate-400">
                      支持 {getTeamName(opinion.support_team_id)} ·{' '}
                      {Math.round(opinion.confidence * 100)}%
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">
                      {opinion.summary}
                    </p>
                  </div>
                ))}
              </div>
              {transcript.judge_decision && (
                <div className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">
                  {transcript.judge_decision.summary}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
