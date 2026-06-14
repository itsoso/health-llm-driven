import type { ProgressCard, ProgressDashboard } from './myProgress';

export type OutcomeProofItemKey = 'graded' | 'improved' | 'verifying' | 'rate';

export interface OutcomeProofItem {
  key: OutcomeProofItemKey;
  label: string;
  value: string;
  accent: boolean;
}

export interface OutcomeProofHighlight {
  title: string;
  detail: string;
}

export interface OutcomeProofSummary {
  title: string;
  subtitle: string;
  route: string;
  items: OutcomeProofItem[];
  highlight: OutcomeProofHighlight | null;
}

export function buildOutcomeProofSummary(
  dashboard: ProgressDashboard | null | undefined,
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
    route: '/my-progress',
    items: [
      { key: 'graded', label: '已验证', value: String(graded), accent: false },
      { key: 'improved', label: '已改善', value: String(improved), accent: improved > 0 },
      { key: 'verifying', label: '验证中', value: String(verifying), accent: verifying > 0 && graded === 0 },
      { key: 'rate', label: '改善率', value: improvementRate, accent: improved > 0 },
    ],
    highlight: pickImprovedHighlight(dashboard?.closed_cards ?? []),
  };
}

function safeRate(rate: number | null | undefined, improved: number, graded: number): string {
  const value = Number.isFinite(rate) ? rate : graded > 0 ? improved / graded : null;
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function pickImprovedHighlight(cards: ProgressCard[]): OutcomeProofHighlight | null {
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
