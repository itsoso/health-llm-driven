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
  equals: '等于',
  takes_medication: '在服用',
  uses_supplement: '在补充',
  has_genotype: '基因型',
  has_history: '病史',
  history_of: '病史',
  has_symptom: '有症状',
  has_allergy: '过敏',
  diagnosed_with: '诊断',
  prefers: '偏好',
  avoids: '避开',
  owns: '持有',
  treats: '用于改善',
  causes: '诱发',
  improves: '改善',
  worsens: '加重',
  triggers: '触发',
  interacts_with: '与其相互作用',
  contraindicated_for: '禁忌于',
  depends_on: '取决于',
  intervention_succeeded: '干预有效',
  intervention_failed: '干预无效',
  contradicts: '与…矛盾',
};

export function predicateLabel(p: string): string {
  return PREDICATE_LABEL[p] || p;
}

/** tier 中文标签 (复用 TIER_LABEL 表, 未知透传). */
export function tierLabel(tier: MemoryTier): string {
  return TIER_LABEL[tier] || tier;
}

/**
 * 衰减后的当前置信度. 后端已在 _to_dict 里算好 effective_confidence,
 * 这里只做兜底 (老 payload / 缺字段时回落到 raw confidence).
 */
export function effectiveConfidence(f: MemoryFact): number {
  return typeof f.effective_confidence === 'number' ? f.effective_confidence : f.confidence;
}

/**
 * 把三元组拼成人读句子: "你的 LDL 高于 3.4 mmol/L".
 * 忠实拼接, 不臆造 —— subject / object_value 原样, predicate 走中文表.
 */
export function factSentence(f: MemoryFact): string {
  const unit = f.object_unit ? ` ${f.object_unit}` : '';
  return `${f.subject} ${predicateLabel(f.predicate)} ${f.object_value}${unit}`.replace(/\s+/g, ' ').trim();
}

/**
 * 低置信折叠阈值. 后端 effective_confidence 有 floor = min(0.4, 0.05×强化次数),
 * 新事实默认 confidence 0.5 起步随时间衰减 —— <0.4 基本是"衰减到底 / 只见过一两次"
 * 的弱信号, 默认收进折叠组防"满屏噪音事实"(简报记忆过度抽取的历史坑).
 */
export const LOW_CONFIDENCE_THRESHOLD = 0.4;

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

/**
 * 用户「确认」一条记忆 —— reinforce (追加来源 + 提升 confidence + 重置衰减时钟).
 * 后端 FactReinforce body: {source_type, source_id?, weight}. 用户确认 = 高权重人工来源.
 * fail-loud: 非 2xx axios 直接 throw, 调用方回滚 + toast.
 */
export async function reinforceFact(
  id: number,
  opts?: { source_type?: string; source_id?: string; weight?: number },
): Promise<MemoryFact> {
  const { data } = await api.post<MemoryFact>(`/memory-facts/${id}/reinforce`, {
    source_type: opts?.source_type ?? 'user_confirmation',
    source_id: opts?.source_id,
    weight: opts?.weight ?? 1.0,
  });
  return data;
}

/**
 * 裁决矛盾: 保留 keepId, 归档 dropId (dropId 被 keepId supersede).
 * 后端路由是 /{old_id}/supersede/{new_id} —— old 被归档, new 保留.
 */
export async function supersedeFact(keepId: number, dropId: number): Promise<void> {
  await api.post(`/memory-facts/${dropId}/supersede/${keepId}`);
}

export interface ContradictionCheckResult {
  count: number;
  contradicting_facts: MemoryFact[];
}

/**
 * 后端矛盾检测端点 (写入前用): 给一个候选三元组, 返回与之矛盾的现有 active facts.
 * 屏内横幅不走这个逐条查 (N 次往返), 而是用 findContradictionPairs 在已拉取列表上本地推导;
 * 保留此包装是为契约对齐 + 未来"新增事实前预检"复用. fail-loud throw.
 */
export async function checkContradictions(
  subject: string,
  predicate: string,
  objectValue: string,
): Promise<ContradictionCheckResult> {
  const { data } = await api.get<ContradictionCheckResult>('/memory-facts/contradictions/check', {
    params: { subject, predicate, object_value: objectValue },
  });
  return data;
}

/**
 * 谓词方向性互斥表 (镜像后端 detect_contradictions 的 contradicting_predicates,
 * 但**只取方向明确互斥的对**). 刻意不含"同谓词不同值"(那多是复查趋势点, 并存合法)
 * 和 is_value×is_above/is_below (数值上可共存: LDL 是 5.0 且 高于 3.4 都为真) ——
 * 保守判定, 避免 over-alarm 把趋势点误报成矛盾.
 */
const CONTRADICTION_MAP: Record<string, string[]> = {
  is_above: ['is_below'],
  is_below: ['is_above'],
  responds_to: ['does_not_respond_to'],
  does_not_respond_to: ['responds_to'],
};

export interface ContradictionPair {
  subject: string;
  a: MemoryFact;
  b: MemoryFact;
}

/**
 * 在已拉取的 active facts 上推导"同 subject、谓词方向互斥"的矛盾对.
 * 纯函数、零网络; 每对只出现一次 (按 id 去重)。
 */
export function findContradictionPairs(facts: MemoryFact[]): ContradictionPair[] {
  const active = facts.filter(f => !f.superseded_at);
  const bySubject = new Map<string, MemoryFact[]>();
  for (const f of active) {
    const list = bySubject.get(f.subject) || [];
    list.push(f);
    bySubject.set(f.subject, list);
  }
  const pairs: ContradictionPair[] = [];
  const seen = new Set<string>();
  for (const [subject, list] of bySubject) {
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i];
        const b = list[j];
        const opposites = CONTRADICTION_MAP[a.predicate];
        if (opposites && opposites.includes(b.predicate)) {
          const key = `${Math.min(a.id, b.id)}:${Math.max(a.id, b.id)}`;
          if (!seen.has(key)) {
            seen.add(key);
            pairs.push({ subject, a, b });
          }
        }
      }
    }
  }
  return pairs;
}
