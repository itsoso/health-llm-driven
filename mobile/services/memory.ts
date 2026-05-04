/**
 * Memory Facts API client — 让用户能"看到 AI 记得我什么".
 *
 * P5 (2026-05-04): 用户有 69 个 memory_facts (semantic 27 / episodic 9 / working 33)
 * 但完全没地方看. 信任建立的关键是"AI 不是黑盒, 我能管教". 这里 list + dismiss
 * 让用户 1) 看见 AI 记得什么 2) 标"这条不对" 让 AI 改.
 */
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
  sources: any[];
  tags: string[];
  is_sensitive: boolean;
  last_reinforced_at?: string | null;
  supersedes_id?: number | null;
  superseded_by_id?: number | null;
  superseded_at?: string | null;
  created_at?: string | null;
}

export interface MemoryStats {
  by_tier: Array<{ tier: MemoryTier; total: number; avg_confidence: number }>;
}

export interface MemoryFiltersIn {
  tier?: MemoryTier;
  predicate?: string;
  tag?: string;
  subject_contains?: string;
  min_confidence?: number;
  limit?: number;
}

/**
 * 拉自己的活跃 facts. 按 effective_confidence 倒序 (后端已排过, 前端再保险一遍).
 */
export async function listMemoryFacts(
  filters?: MemoryFiltersIn,
): Promise<MemoryFact[]> {
  const params = new URLSearchParams();
  if (filters?.tier) params.set('tier', filters.tier);
  if (filters?.predicate) params.set('predicate', filters.predicate);
  if (filters?.tag) params.set('tag', filters.tag);
  if (filters?.subject_contains) params.set('subject_contains', filters.subject_contains);
  if (filters?.min_confidence !== undefined) params.set('min_confidence', String(filters.min_confidence));
  if (filters?.limit) params.set('limit', String(filters.limit));

  const qs = params.toString();
  const url = qs ? `/memory-facts/me?${qs}` : '/memory-facts/me';
  const res = await api.get<MemoryFact[]>(url);
  return Array.isArray(res.data) ? res.data : [];
}

/**
 * 用户标 "这条不对" — soft-delete (写 superseded_at + 不再注入 prompt).
 * 失败抛, 调用方决定 toast.
 */
export async function dismissMemoryFact(id: number, reason: string = 'user_dismissed'): Promise<void> {
  await api.post(`/memory-facts/${id}/dismiss?reason=${encodeURIComponent(reason)}`);
}

/**
 * stats — 用于顶部 "AI 记得你 N 条" header.
 */
export async function getMemoryStats(): Promise<MemoryStats> {
  const res = await api.get<MemoryStats>('/memory-facts/stats/me');
  return res.data || { by_tier: [] };
}

// ─────────────── 中文翻译 + 主题分组 ───────────────

/** predicate 中文标签. 不在表里的 predicate 走 raw 显示. */
export function predicateLabel(predicate: string): string {
  return PREDICATE_LABELS[predicate] || predicate;
}

const PREDICATE_LABELS: Record<string, string> = {
  has_symptom: '症状',
  takes_medication: '在服用',
  has_allergy: '过敏',
  prefers: '偏好',
  avoids: '避开',
  history_of: '病史',
  responds_to: '反应',
  has_genotype: '基因型',
  diagnosed_with: '诊断',
  uses_supplement: '补剂',
  contraindicated_for: '禁忌',
  treats: '治疗',
  causes: '触发',
  triggers: '诱发',
  interacts_with: '互作',
  owns: '持有',
};

/** tier 中文标签. */
export function tierLabel(tier: MemoryTier): string {
  return ({
    working: '临时',
    episodic: '近期',
    semantic: '长期',
    procedural: '习惯',
  } as Record<MemoryTier, string>)[tier] || tier;
}

/** 按 predicate 分组 (用于"主题分类" 视图). 返回保留原顺序. */
export function groupByPredicate(facts: MemoryFact[]): Array<{ predicate: string; label: string; facts: MemoryFact[] }> {
  const map = new Map<string, MemoryFact[]>();
  for (const f of facts) {
    const list = map.get(f.predicate) || [];
    list.push(f);
    map.set(f.predicate, list);
  }
  return Array.from(map.entries()).map(([predicate, fs]) => ({
    predicate,
    label: predicateLabel(predicate),
    facts: fs,
  }));
}
