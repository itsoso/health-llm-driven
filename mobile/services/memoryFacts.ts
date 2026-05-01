import api from './api';

export type MemoryTier = 'working' | 'episodic' | 'semantic' | 'procedural';

export interface MemoryFact {
  id: number;
  tier: MemoryTier;
  subject: string;
  predicate: string;
  object_value: string;
  object_unit?: string | null;
  confidence: number;
  effective_confidence: number;
  reinforcement_count: number;
  decay_rate: number;
  sources: Array<{ type: string; id?: string | number | null; weight?: number; reason?: string; at?: string }>;
  tags: string[];
  is_sensitive: boolean;
  last_reinforced_at: string | null;
  supersedes_id: number | null;
  superseded_by_id: number | null;
  superseded_at: string | null;
  created_at: string | null;
}

export interface MemoryStats {
  by_tier: Array<{ tier: MemoryTier; total: number; avg_confidence: number }>;
}

export const TIER_LABEL: Record<MemoryTier, string> = {
  working: '当前观察',
  episodic: '近期片段',
  semantic: '长期事实',
  procedural: '行为模式',
};

export const TIER_COLOR: Record<MemoryTier, string> = {
  working: '#8E8E93',
  episodic: '#007AFF',
  semantic: '#34C759',
  procedural: '#AF52DE',
};

// 已知 predicate 的中文标签; 未知的直接透传
const PREDICATE_LABEL: Record<string, string> = {
  responds_to: '对其响应良好',
  does_not_respond_to: '对其无响应',
  partially_responds_to: '部分响应',
  is_above: '高于',
  is_below: '低于',
  is_value: '值为',
  takes_medication: '在服用',
  has_genotype: '基因型',
  has_history: '病史',
  improves: '改善',
  worsens: '加重',
  triggers: '触发',
  contradicts: '与…矛盾',
};

export function predicateLabel(p: string): string {
  return PREDICATE_LABEL[p] || p;
}

export function sourceTypeLabel(t: string): string {
  switch (t) {
    case 'action_card_outcome': return 'AI 建议回看';
    case 'medical_exam': return '化验';
    case 'medical_exam_item': return '化验';
    case 'specialist_finding': return 'Specialist 观察';
    case 'soap_entry': return '诊疗记录';
    case 'user_directive': return '用户指令';
    case 'manual': return '手动添加';
    case 'user_dismissal': return '用户否认';
    default: return t;
  }
}

export function primarySourceType(f: MemoryFact): string {
  const nonDismissal = (f.sources || []).find(s => s.type !== 'user_dismissal');
  return nonDismissal?.type || (f.sources?.[0]?.type ?? 'manual');
}

export async function listMyFacts(params?: {
  tier?: MemoryTier;
  min_confidence?: number;
  limit?: number;
}): Promise<MemoryFact[]> {
  const { data } = await api.get<MemoryFact[]>('/memory-facts/me', { params });
  return data;
}

export async function getMyStats(): Promise<MemoryStats> {
  const { data } = await api.get<MemoryStats>('/memory-facts/stats/me');
  return data;
}

export async function dismissFact(id: number, reason = 'user_dismissed'): Promise<void> {
  await api.post(`/memory-facts/${id}/dismiss`, null, { params: { reason } });
}
