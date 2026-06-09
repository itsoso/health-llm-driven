import api from './api';

// 冷启动信息增益:下一步补哪项数据(后端 /twin/me/next-data)
export interface NextDataSuggestion {
  item: string;
  unlocks: string;
  priority: number;
  missing_count?: number;
  have_count?: number;
  route?: string; // 该建议对应的目标路由(后端给;前端 ?? fallback)
}
export interface NextDataResponse {
  suggestions: NextDataSuggestion[];
  note?: string;
}

export async function getNextData(): Promise<NextDataResponse> {
  const { data } = await api.get<NextDataResponse>('/twin/me/next-data');
  return data;
}

// 因果记忆:事件×指标变化(后端 /personal-outcome/me/causal-notes)
export interface CausalNote {
  metric: string;
  before: number;
  after: number;
  pct: number;
  direction: string; // 改善 / 走低
  text: string;
}
export interface CausalNotesResponse {
  notes: CausalNote[];
  evidence_tier?: string;
  claim_boundary?: string;
}

export async function getCausalNotes(): Promise<CausalNotesResponse> {
  const { data } = await api.get<CausalNotesResponse>('/personal-outcome/me/causal-notes');
  return data;
}

// ── 纯 helper(UI 无关,可单测)──

/** 取信息增益最高的一条建议(按 priority 降序);无 → null。 */
export function topNextData(resp: NextDataResponse | null | undefined): NextDataSuggestion | null {
  const list = resp?.suggestions ?? [];
  if (list.length === 0) return null;
  return [...list].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))[0];
}

/** 取最近一条"改善"的因果记忆优先;无改善则取第一条;空 → null。 */
export function pickCausalHighlight(resp: CausalNotesResponse | null | undefined): CausalNote | null {
  const notes = resp?.notes ?? [];
  if (notes.length === 0) return null;
  return notes.find((n) => n.direction === '改善') ?? notes[0];
}
