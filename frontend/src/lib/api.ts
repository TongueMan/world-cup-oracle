import type {
  TournamentPrediction,
  GroupStanding,
  MatchDetail,
  DataQualityReport,
  HealthStatus,
  BingKnowledgeResponse,
  WorldCupMatch,
  WorldCupSyncStatus,
  WorldCupStanding,
  WorldCupPlayerStat,
} from './types';

const API_BASE = '/api';

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail =
        typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

async function postJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, { method: 'POST' });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail =
        typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getTournament: () => fetchJSON<TournamentPrediction>('/predictions/tournament'),
  getGroups: () => fetchJSON<GroupStanding[]>('/groups'),
  getGroup: (group: string) => fetchJSON<GroupStanding>(`/groups/${group}`),
  getMatch: (matchId: string) => fetchJSON<MatchDetail>(`/matches/${matchId}`),
  getDebate: (matchId: string) => fetchJSON(`/agents/debate/${matchId}`),
  generateDebate: (matchId: string) => postJSON(`/agents/debate/match?match_id=${matchId}`),
  getDataStatus: () => fetchJSON<DataQualityReport>('/data/status'),
  getBingKnowledge: (limit: number = 8) => fetchJSON<BingKnowledgeResponse>(`/knowledge/bing?limit=${limit}`),
  getWorldCupMatches: () => fetchJSON<WorldCupMatch[]>('/worldcup/matches'),
  getWorldCupBracket: () => fetchJSON<WorldCupMatch[]>('/worldcup/bracket'),
  getWorldCupStandings: () => fetchJSON<WorldCupStanding[]>('/worldcup/standings'),
  getWorldCupPlayerStats: () => fetchJSON<WorldCupPlayerStat[]>('/worldcup/player-stats'),
  getWorldCupSyncStatus: () => fetchJSON<WorldCupSyncStatus>('/worldcup/sync/status'),
  syncWorldCup: () => postJSON('/worldcup/admin/sync'),
  runPrediction: (seed: number = 42, mode: string = 'balanced') =>
    postJSON(`/predictions/run?seed=${seed}&mode=${mode}`),
  runFullPrediction: (seed: number = 42, mode: string = 'balanced') =>
    postJSON(`/predict/tournament?seed=${seed}&mode=${mode}`),
  health: () => fetchJSON<HealthStatus>('/health'),
};
