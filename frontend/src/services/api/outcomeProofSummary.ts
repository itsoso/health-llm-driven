import { api } from './client';

export type ProgressOutcome = 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;

export interface ProgressCard {
  id: number;
  title: string;
  status?: string | null;
  user_decision?: string | null;
  outcome?: ProgressOutcome;
  effect_size?: number | null;
  accuracy_score?: number | null;
  metric_key?: string | null;
  baseline_value?: string | null;
  actual_value?: string | null;
  evidence_level?: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  created_at?: string | null;
  completed_at?: string | null;
  graded_at?: string | null;
}

export interface ProgressDashboard {
  window: { since: string; until: string; days: number };
  stats: {
    total_surfaced: number;
    accepted: number;
    declined: number;
    pending: number;
    completed: number;
    graded: number;
    improved: number;
    unchanged: number;
    worsened: number;
    inconclusive: number;
    safe_closed: number;
    acceptance_rate: number | null;
    verification_rate: number | null;
    improvement_rate: number | null;
  };
  closed_cards: ProgressCard[];
  verifying_cards: ProgressCard[];
}

export interface OutcomeProofItem {
  key: 'graded' | 'improved' | 'verifying' | 'rate';
  label: string;
  value: string;
  accent: boolean;
}

export interface OutcomeProofSummary {
  title: string;
  subtitle: string;
  href: string;
  items: OutcomeProofItem[];
  highlight: { title: string; detail: string } | null;
}

export function buildOutcomeProofSummary(
  dashboard: ProgressDashboard | null | undefined
): OutcomeProofSummary {
  const stats = dashboard?.stats;
  const graded = Math.max(0, stats?.graded ?? 0);
  const improved = Math.max(0, stats?.improved ?? 0);
  const verifying = Math.max(0, dashboard?.verifying_cards?.length ?? 0);
  const total = Math.max(0, stats?.total_surfaced ?? 0);
  const improvementRate = safeRate(stats?.improvement_rate, improved, graded);

  let title: string;
  let subtitle: string;
  if (graded > 0 && improved > 0) {
    title = `个人证据：${improved} 项已改善`;
    subtitle = `已验证 ${graded} 项，${improved}/${graded} 对你有效。`;
  } else if (graded > 0) {
    title = `个人证据：${graded} 项已验证`;
    subtitle = '暂未看到明确改善，下一轮会调整干预。';
  } else if (verifying > 0) {
    title = '个人证据验证中';
    subtitle = `${verifying} 个干预已完成，等待指标变化。`;
  } else if (total > 0) {
    title = '个人证据待完成';
    subtitle = `${total} 条建议正在推进，完成后才会进入验证。`;
  } else {
    title = '等待第一个验证闭环';
    subtitle = '接受并完成建议后，这里会显示对你是否有效。';
  }

  return {
    title,
    subtitle,
    href: '/my-progress',
    items: [
      { key: 'graded', label: '已验证', value: String(graded), accent: false },
      { key: 'improved', label: '已改善', value: String(improved), accent: improved > 0 },
      { key: 'verifying', label: '验证中', value: String(verifying), accent: verifying > 0 && graded === 0 },
      { key: 'rate', label: '改善率', value: improvementRate, accent: improved > 0 },
    ],
    highlight: pickImprovedHighlight(dashboard?.closed_cards ?? []),
  };
}

export async function getOutcomeProofSummary(days = 30): Promise<OutcomeProofSummary> {
  const { data } = await api.get<ProgressDashboard>(`/action-cards/me/progress?days=${days}`);
  return buildOutcomeProofSummary(data);
}

function safeRate(rate: number | null | undefined, improved: number, graded: number): string {
  const value = Number.isFinite(rate) ? rate : graded > 0 ? improved / graded : null;
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function pickImprovedHighlight(cards: ProgressCard[]): OutcomeProofSummary['highlight'] {
  const card = cards.find((item) => item.outcome === 'improved') ?? null;
  if (!card) return null;
  const metric = card.metric_key || '指标';
  const detail = card.baseline_value && card.actual_value
    ? `${metric} ${card.baseline_value} → ${card.actual_value}`
    : metric;
  return {
    title: card.title,
    detail,
  };
}
