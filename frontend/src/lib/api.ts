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
  PredictionRunResult,
  PredictionSnapshot,
  PredictionStageAvailability,
  MatchEnvironment,
  PredictionAgentReport,
} from './types';

const API_BASE = '/api';

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, statusText: string, detail: unknown) {
    super(readableErrorMessage(status, statusText, detail));
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function readableErrorMessage(status: number, statusText: string, detail: unknown) {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const payload = detail as { message?: unknown; status?: unknown };
    if (typeof payload.message === 'string') return payload.message;
    if (payload.status === 'verified_prediction_unavailable' || payload.status === 'published_prediction_unavailable') {
      return '该阶段暂无通过验证的预测报告。';
    }
  }
  return `${status} ${statusText}`;
}

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`);
  if (!res.ok) {
    let detail: unknown = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      // keep default detail
    }
    throw new ApiError(res.status, res.statusText, detail);
  }
  return res.json() as Promise<T>;
}

async function postJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, { method: 'POST' });
  if (!res.ok) {
    let detail: unknown = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      // keep default detail
    }
    throw new ApiError(res.status, res.statusText, detail);
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
    let detail: unknown = `${res.status} ${res.statusText}`;
    try {
      const payload = await res.json();
      detail = payload.detail ?? payload;
    } catch {
      // keep default detail
    }
    throw new ApiError(res.status, res.statusText, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getTournament: (anchor = 'current') =>
    fetchJSON<TournamentPrediction>(`/predictions/tournament?anchor=${encodeURIComponent(anchor)}`),
  getPredictionCandidate: (anchor = 'current') =>
    fetchJSON<TournamentPrediction>(`/predictions/candidate?anchor=${encodeURIComponent(anchor)}`),
  getPredictionSnapshots: () => fetchJSON<PredictionSnapshot[]>('/predictions/snapshots'),
  getPredictionStages: () => fetchJSON<PredictionStageAvailability[]>('/predictions/stages'),
  getPredictionSnapshot: (artifactId: string) =>
    fetchJSON<TournamentPrediction>(`/predictions/snapshots/${encodeURIComponent(artifactId)}`),
  getPredictionReport: (artifactId: string) =>
    fetchJSON<PredictionAgentReport>(`/predictions/reports/${encodeURIComponent(artifactId)}`),
  getArtifactMatch: (artifactId: string, matchId: string) =>
    fetchJSON<MatchDetail>(`/predictions/artifacts/${encodeURIComponent(artifactId)}/matches/${encodeURIComponent(matchId)}`),
  getGroups: () => fetchJSON<GroupStanding[]>('/groups'),
  getGroup: (group: string) => fetchJSON<GroupStanding>(`/groups/${group}`),
  getMatch: (matchId: string) => fetchJSON<MatchDetail>(`/matches/${matchId}`),
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
  getMatchEnvironment: (matchId: string) =>
    fetchJSON<MatchEnvironment>(`/worldcup/matches/${encodeURIComponent(matchId)}/environment`),
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
  runPrediction: (anchor = 'current') =>
    postJSON<PredictionRunResult>(`/predictions/run?anchor=${encodeURIComponent(anchor)}&seed=42&mode=professional&strict=true`),
  runFullPrediction: (anchor = 'current') =>
    postJSON<PredictionRunResult>(`/predict/tournament?anchor=${encodeURIComponent(anchor)}&seed=42&mode=professional&precompute_agents=false&strict=true`),
  health: () => fetchJSON<HealthStatus>('/health'),
};
