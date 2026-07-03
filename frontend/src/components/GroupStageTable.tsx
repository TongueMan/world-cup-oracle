import type { GroupStanding, GroupStandingRow } from '../lib/types';
import { getTeamName } from '../lib/constants';

interface GroupStageTableProps {
  standings: GroupStanding[];
}

function TableRow({ row, qualified }: { row: GroupStandingRow; qualified: boolean }) {
  return (
    <tr className={qualified ? 'bg-emerald-50' : ''}>
      <td className="px-2 py-1.5 text-center text-sm text-slate-400">
        {qualified && <span className="text-emerald-600">●</span>} {row.rank}
      </td>
      <td className="px-2 py-1.5 text-left text-sm font-medium text-slate-800">
        <span className="text-xs text-slate-400">{row.team_id}</span>{' '}
        {getTeamName(row.team_id)}
      </td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">{row.played}</td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">{row.won}</td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">{row.drawn}</td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">{row.lost}</td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">{row.goals_for}</td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">{row.goals_against}</td>
      <td className="px-2 py-1.5 text-center text-sm text-slate-600">
        {row.goal_difference > 0 ? '+' : ''}
        {row.goal_difference}
      </td>
      <td className="px-2 py-1.5 text-center text-sm font-bold text-slate-800">
        {row.points}
      </td>
    </tr>
  );
}

function GroupCard({ standing }: { standing: GroupStanding }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="bg-slate-800 px-3 py-2 text-sm font-bold text-white">
        小组 {standing.group}
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
            <th className="px-2 py-1.5 text-center font-medium">排名</th>
            <th className="px-2 py-1.5 text-left font-medium">球队</th>
            <th className="px-2 py-1.5 text-center font-medium">场</th>
            <th className="px-2 py-1.5 text-center font-medium">胜</th>
            <th className="px-2 py-1.5 text-center font-medium">平</th>
            <th className="px-2 py-1.5 text-center font-medium">负</th>
            <th className="px-2 py-1.5 text-center font-medium">进</th>
            <th className="px-2 py-1.5 text-center font-medium">失</th>
            <th className="px-2 py-1.5 text-center font-medium">净</th>
            <th className="px-2 py-1.5 text-center font-medium">分</th>
          </tr>
        </thead>
        <tbody>
          {standing.rows.map((row) => (
            <TableRow key={row.team_id} row={row} qualified={row.rank <= 2} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GroupStageTable({ standings }: GroupStageTableProps) {
  if (!standings || standings.length === 0) {
    return (
      <section>
        <h2 className="mb-4 text-xl font-bold text-slate-800">小组赛积分</h2>
        <p className="py-8 text-center text-slate-400">暂无小组数据</p>
      </section>
    );
  }

  return (
    <section>
      <h2 className="mb-4 text-xl font-bold text-slate-800">小组赛积分</h2>
      <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
        <span className="inline-block h-3 w-3 rounded bg-emerald-50 ring-1 ring-emerald-300" />
        绿色背景 = 出线（前两名）
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {standings.map((standing) => (
          <GroupCard key={standing.group} standing={standing} />
        ))}
      </div>
    </section>
  );
}
