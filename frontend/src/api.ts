import type { AnalysisRequest, AnalyzeResponse, CatalogResponse, HealthResponse, MatchesResponse, PlayersResponse, RosterResponse, TeamResponse } from './types';

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly detail?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item: unknown) => {
    if (item && typeof item === 'object' && 'msg' in item) return String(item.msg);
    return String(item);
  }).join('；');
  return '请求未完成，请检查输入并重试。';
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } });
  } catch (error) {
    if (typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError') throw error;
    throw new ApiError('无法连接真实模型服务，请确认后端已启动。不会生成替代预测。', 0);
  }
  let data: unknown;
  try { data = await response.json(); } catch { throw new ApiError('服务返回了无法识别的响应，未生成预测。', response.status); }
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : data;
    throw new ApiError(detailMessage(detail), response.status, detail);
  }
  return data as T;
}

function query(params: Record<string, string | number | boolean>): string {
  return new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)])).toString();
}

export const api = {
  health: () => request<HealthResponse>('/health'),
  catalog: (asOf: string) => request<CatalogResponse>(`/catalog?${query({ as_of: asOf })}`),
  teams: (asOf: string, worldsOnly: boolean, search = '') => request<TeamResponse>(`/teams?${query({ as_of: asOf, worlds_only: worldsOnly, query: search })}`),
  roster: (teamId: string, asOf: string) => request<RosterResponse>(`/teams/${encodeURIComponent(teamId)}/roster?${query({ as_of: asOf })}`),
  matches: (asOf: string, worldsOnly: boolean) => request<MatchesResponse>(`/matches?${query({ as_of: asOf, worlds_only: worldsOnly })}`),
  players: (search: string, asOf: string) => request<PlayersResponse>(`/players?${query({ query: search, as_of: asOf })}`),
  analyze: (payload: AnalysisRequest, signal?: AbortSignal) => request<AnalyzeResponse>('/analyze', { method: 'POST', body: JSON.stringify(payload), signal }),
};
