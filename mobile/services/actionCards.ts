import api from './api';
import type { SafetyAlert } from './safety';
import { normalizeInterventionDraft, type InterventionDraft } from './interventionDraft';
import type { OutcomeReviewDraft } from './outcomeReview';

export type ActionCardMetricKey =
  | 'sleep_score' | 'hrv' | 'rhr' | 'weight' | 'bp' | 'spo2_odi' | 'custom'
  // 化验项
  | 'alt' | 'ast' | 'ggt' | 'alp' | 'creatinine' | 'uric_acid' | 'urea'
  | 'hba1c' | 'tsh' | 'ft3' | 'ft4' | 'vitamin_d' | 'b12' | 'ferritin'
  | 'crp' | 'esr' | 'wbc' | 'rbc' | 'hgb' | 'plt' | 'lp_a' | 'apo_b'
  // 血脂血糖
  | 'ldl' | 'hdl' | 'tc' | 'tg' | 'fasting_glucose' | 'blood_glucose'
  | 'systolic_bp' | 'diastolic_bp' | 'bmi' | 'body_fat';

export interface ActionCard {
  id: number;
  title: string;
  content: string;
  card_type: string;
  status: string;
  priority: number;
  created_at: string;
  expires_at?: string | null;
  completed_at?: string | null;
  checklist?: { item: string; done: boolean }[];
  latest_assessment?: {
    score?: number;
    summary?: string;
    evidence?: string[];
    adjustments?: string[];
  } | null;
  source_type?: string;
  source_id?: string | null;
  metric_key?: ActionCardMetricKey | null;
  baseline_value?: string | null;
  target_value?: string | null;
  verification_days?: number | null;
  // 信任循环字段 (Specialist 信用)
  creator_specialist?: string | null;
  check_back_date?: string | null;
  actual_value?: string | null;
  accuracy_score?: number | null;
  graded_at?: string | null;
  grading_notes?: string | null;
  // WSCLA 生命周期 (Phase 0/1)
  severity?: 'critical' | 'high' | 'medium' | 'low' | 'info' | null;
  // 2026-05-12: 证据等级
  evidence_level?: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  evidence_refs?: string[];
  user_decision?: 'accepted' | 'adjusted' | 'declined' | 'dismissed' | 'false_positive' | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  outcome?: 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;
  effect_size?: number | null;
  seen_at?: string | null;
  push_sent_at?: string | null;
  push_delivered_at?: string | null;
  push_clicked_at?: string | null;
  adherence_kind?: 'self_reported' | 'device' | 'proxy' | string | null;
  adherence_confidence?: number | null;
}

export type CardDecision = 'accepted' | 'adjusted' | 'declined' | 'dismissed' | 'false_positive';

export interface ActionCardCreateInput {
  title: string;
  content: string;
  card_type?: string;
  color?: string;
  source_type?: string;
  source_id?: string | null;
  priority?: number;
  expires_at?: string | null;
  metric_key?: ActionCardMetricKey;
  baseline_value?: string;
  target_value?: string;
  verification_days?: number;
  checklist?: { item: string; done: boolean }[];
  evidence_refs?: string[];
  /** Explicit user confirmation: create and accept in the same backend transaction. */
  accepted?: boolean;
}

export type ActionCockpitItem =
  | { type: 'alert'; item: SafetyAlert }
  | { type: 'card'; item: ActionCard };

export interface ActionCockpitSection {
  title: '需要立即处理' | '正在执行' | '等待验证' | '日常提示';
  data: ActionCockpitItem[];
}

function getSeverityKey(severity: unknown): string {
  return typeof severity === 'string' ? severity : (severity as { label?: string } | undefined)?.label ?? 'info';
}

export function getActionCardProgress(card: ActionCard): { completed: number; total: number } | null {
  const checklist = getActionCardChecklist(card);
  if (checklist.length === 0) return null;
  return {
    completed: checklist.filter(item => item.done).length,
    total: checklist.length,
  };
}

/**
 * 后端历史行动卡可能带空字符串 checklist 占位项。
 * 空项不是用户步骤:不应参与进度,也不应渲染成空圆点。
 */
export function getActionCardChecklist(card: ActionCard): { item: string; done: boolean }[] {
  if (!Array.isArray(card.checklist)) return [];
  return card.checklist.filter(item => typeof item?.item === 'string' && item.item.trim().length > 0);
}

export function getActionCardVerificationLabel(card: ActionCard): string | null {
  if (card.latest_assessment?.score != null) {
    return `已评估 ${card.latest_assessment.score}/10`;
  }
  if (card.expires_at) {
    return `待验证 ${card.expires_at.slice(0, 10)}`;
  }
  return null;
}

export function pickWeeklySuggestionCards(cards: ActionCard[] = [], limit = 5): ActionCard[] {
  const now = Date.now();
  return cards
    .filter(card => {
      if (card.source_type !== 'weekly_advisor') return false;
      if (card.status && card.status !== 'active') return false;
      if (card.user_decision) return false;
      if (card.expires_at) {
        const expiresAt = Date.parse(card.expires_at);
        if (!Number.isNaN(expiresAt) && expiresAt <= now) return false;
      }
      return true;
    })
    .slice(0, limit);
}

export function buildActionCockpitSections(
  alerts: SafetyAlert[] = [],
  cards: ActionCard[] = [],
): ActionCockpitSection[] {
  const sortedAlerts = [...alerts].sort((a, b) => {
    const order = ['critical', 'high', 'medium', 'low', 'info'];
    return order.indexOf(getSeverityKey(a.severity)) - order.indexOf(getSeverityKey(b.severity));
  });

  const immediateAlerts = sortedAlerts.filter(alert => ['critical', 'high'].includes(getSeverityKey(alert.severity)));
  const dailyAlerts = sortedAlerts.filter(alert => !['critical', 'high'].includes(getSeverityKey(alert.severity)));
  const verificationCards = cards.filter(card => card.latest_assessment || card.expires_at);
  const activeCards = cards.filter(card => !card.latest_assessment && !card.expires_at);

  return [
    { title: '需要立即处理' as const, data: immediateAlerts.map(item => ({ type: 'alert' as const, item })) },
    { title: '正在执行' as const, data: activeCards.map(item => ({ type: 'card' as const, item })) },
    { title: '等待验证' as const, data: verificationCards.map(item => ({ type: 'card' as const, item })) },
    { title: '日常提示' as const, data: dailyAlerts.map(item => ({ type: 'alert' as const, item })) },
  ].filter(section => section.data.length > 0);
}

export async function getActiveCards(): Promise<ActionCard[]> {
  const { data } = await api.get<ActionCard[]>(
    '/action-cards/me?status=active&limit=20',
  );
  return data;
}

export async function completeCard(id: number): Promise<ActionCard> {
  const { data } = await api.patch<ActionCard>(`/action-cards/${id}`, {
    status: 'completed',
  });
  return data;
}

/**
 * P8 (2026-05-04): 撤销"标记完成" — status 改回 active, 后端会清 completed_at.
 * 用于 toast undo 5s 内点击.
 */
export async function reactivateCard(id: number): Promise<ActionCard> {
  const { data } = await api.patch<ActionCard>(`/action-cards/${id}`, {
    status: 'active',
  });
  return data;
}

export async function createActionCard(input: ActionCardCreateInput): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>('/action-cards', input);
  return data;
}

export async function createInterventionDraft(draft: InterventionDraft): Promise<ActionCard> {
  return createActionCard(normalizeInterventionDraft(draft));
}

export async function reviewActionCard(id: number, draft: OutcomeReviewDraft): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>(`/action-cards/${id}/review`, {
    status: 'completed',
    outcome_status: draft.status,
    actual_value: draft.actualValue || undefined,
    latest_assessment: {
      score: scoreFromOutcomeStatus(draft.status),
      summary: draft.summary,
      evidence: draft.evidence,
    },
  });
  return data;
}

export async function recordCardAdherence(
  cardId: number,
  confidence: number,
  kind: 'self_reported' | 'device' | 'proxy' = 'self_reported',
): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>(`/action-cards/${cardId}/adherence`, {
    kind,
    confidence,
  });
  return data;
}

function scoreFromOutcomeStatus(status: OutcomeReviewDraft['status']): number {
  if (status === 'met') return 8;
  if (status === 'not_met') return 3;
  if (status === 'inconclusive') return 5;
  return 0;
}

/**
 * P1-4 (2026-05-11): 用户对卡片做决策 — accepted / adjusted / declined / dismissed / false_positive.
 * 后端落 user_decision + decided_at + decision_reason. declined / dismissed / false_positive 自动归档.
 */
export async function recordCardDecision(
  cardId: number,
  decision: CardDecision,
  reason?: string,
  adjustedPayload?: Record<string, unknown>,
): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>(`/action-cards/${cardId}/decision`, {
    decision,
    reason,
    adjusted_payload: adjustedPayload,
  });
  return data;
}

/**
 * P1-5 (2026-05-11): 通知点击回写 — 客户端打开 health://card/{id} 深链时调.
 * 后端落 push_clicked_at + seen_at, 已 stamp 不覆盖.
 * 失败静默 (旁路语义): 是埋点, 不该影响用户打开页面.
 */
export async function recordCardPushClick(cardId: number): Promise<void> {
  try {
    await api.post(`/action-cards/${cardId}/click`);
  } catch (err) {
    // 失败不抛, 不影响 UI
    console.warn('[actionCards] click 回写失败', err);
  }
}
