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
  WorldCupHistoryEdition,
  WorldCupHistoryEditionDetail,
  WorldCupHistoryMatch,
  AgentCapabilities,
  AgentLLMConfig,
  AgentMatchToolResponse,
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

async function postBodyJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const payload = await res.json();
      detail =
        typeof payload.detail === 'string'
          ? payload.detail
          : JSON.stringify(payload.detail ?? payload);
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
  getAgentCapabilities: () => fetchJSON<AgentCapabilities>('/agents/capabilities'),
  testAgentProvider: (llmConfig: AgentLLMConfig) =>
    postBodyJSON<{ ok: boolean; message: string }>('/agents/providers/test', { llmConfig }),
  analyzeMatchWithAgent: (matchId: string, llmConfig: AgentLLMConfig, question = '') =>
    postBodyJSON<AgentMatchToolResponse>(`/agents/matches/${encodeURIComponent(matchId)}/analyze`, {
      llmConfig,
      question,
    }),
  generateMatchAgentReport: (matchId: string, llmConfig: AgentLLMConfig, question = '') =>
    postBodyJSON<AgentMatchToolResponse>(`/agents/matches/${encodeURIComponent(matchId)}/report`, {
      llmConfig,
      question,
    }),
  searchMatchNews: (matchId: string, llmConfig: AgentLLMConfig, question = '') =>
    postBodyJSON<AgentMatchToolResponse>(`/agents/matches/${encodeURIComponent(matchId)}/search-news`, {
      llmConfig,
      question,
    }),
  analyzeMatchEnvironment: (matchId: string, llmConfig: AgentLLMConfig, question = '') =>
    postBodyJSON<AgentMatchToolResponse>(`/agents/matches/${encodeURIComponent(matchId)}/environment`, {
      llmConfig,
      question,
    }),
  getDataStatus: () => fetchJSON<DataQualityReport>('/data/status'),
  getBingKnowledge: (limit: number = 8) => fetchJSON<BingKnowledgeResponse>(`/knowledge/bing?limit=${limit}`),
  getWorldCupMatches: () => fetchJSON<WorldCupMatch[]>('/worldcup/matches'),
  getWorldCupBracket: () => fetchJSON<WorldCupMatch[]>('/worldcup/bracket'),
  getWorldCupStandings: () => fetchJSON<WorldCupStanding[]>('/worldcup/standings'),
  getWorldCupPlayerStats: () => fetchJSON<WorldCupPlayerStat[]>('/worldcup/player-stats'),
  getWorldCupSyncStatus: () => fetchJSON<WorldCupSyncStatus>('/worldcup/sync/status'),
  getWorldCupHistoryEditions: () => fetchJSON<WorldCupHistoryEdition[]>('/worldcup/history/editions'),
  getWorldCupHistoryEdition: (year: number) =>
    fetchJSON<WorldCupHistoryEditionDetail>(`/worldcup/history/editions/${year}`),
  getWorldCupHistoryEditionMatches: (year: number, params: { team?: string; stage?: string; homeTeam?: string; awayTeam?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.team) search.set('team', params.team);
    if (params.stage) search.set('stage', params.stage);
    if (params.homeTeam) search.set('homeTeam', params.homeTeam);
    if (params.awayTeam) search.set('awayTeam', params.awayTeam);
    const suffix = search.toString() ? `?${search}` : '';
    return fetchJSON<WorldCupHistoryMatch[]>(`/worldcup/history/editions/${year}/matches${suffix}`);
  },
  getWorldCupHistoryMatches: (params: { year?: number; team?: string; stage?: string; homeTeam?: string; awayTeam?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.year != null) search.set('year', String(params.year));
    if (params.team) search.set('team', params.team);
    if (params.stage) search.set('stage', params.stage);
    if (params.homeTeam) search.set('homeTeam', params.homeTeam);
    if (params.awayTeam) search.set('awayTeam', params.awayTeam);
    const suffix = search.toString() ? `?${search}` : '';
    return fetchJSON<WorldCupHistoryMatch[]>(`/worldcup/history/matches${suffix}`);
  },
  getWorldCupHistoryTeamMatches: (team: string) =>
    fetchJSON<WorldCupHistoryMatch[]>(`/worldcup/history/teams/${encodeURIComponent(team)}/matches`),
  getWorldCupHistoryFinals: () => fetchJSON<WorldCupHistoryMatch[]>('/worldcup/history/finals'),
  syncWorldCup: () => postJSON('/worldcup/admin/sync'),
  runPrediction: (seed: number = 42, mode: string = 'balanced') =>
    postJSON(`/predictions/run?seed=${seed}&mode=${mode}`),
  runFullPrediction: (seed: number = 42, mode: string = 'balanced') =>
    postJSON(`/predict/tournament?seed=${seed}&mode=${mode}`),
  health: () => fetchJSON<HealthStatus>('/health'),
};
