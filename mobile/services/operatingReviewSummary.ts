import { fetchHealthOperatingReview, type HealthOperatingReview } from './healthOperatingReview';

export type { HealthOperatingReview };

export type OperatingReviewItemKey = 'completion_rate' | 'completed' | 'total' | 'learnable';

export interface OperatingReviewItem {
  key: OperatingReviewItemKey;
  label: string;
  value: string;
  accent: boolean;
}

export interface OperatingReviewHighlight {
  label: string;
  value: string;
  detail: string;
  positive: boolean;
}

export interface OperatingReviewSummary {
  title: string;
  subtitle: string;
  route: string;
  items: OperatingReviewItem[];
  highlight: OperatingReviewHighlight | null;
}

interface MetricMeta {
  label: string;
  unit: string;
  good: 'up' | 'down';
}

const METRIC_META: Record<string, MetricMeta> = {
  weight: { label: '体重', unit: 'kg', good: 'down' },
  waist_cm: { label: '腰围', unit: 'cm', good: 'down' },
  systolic_bp: { label: '收缩压', unit: 'mmHg', good: 'down' },
  diastolic_bp: { label: '舒张压', unit: 'mmHg', good: 'down' },
  sleep_score: { label: '睡眠评分', unit: '', good: 'up' },
  hrv: { label: 'HRV', unit: 'ms', good: 'up' },
};

export function buildOperatingReviewSummary(review: HealthOperatingReview | null | undefined): OperatingReviewSummary {
  const total = Math.max(0, review?.execution?.total_events ?? 0);
  const completed = Math.max(0, review?.execution?.completed_events ?? 0);
  const learnable = Math.max(0, review?.completed_action_keys?.length ?? 0);
  const completionRate = clampRate(review?.execution?.completion_rate ?? 0);
  const rateLabel = `${Math.round(completionRate * 100)}%`;

  return {
    title: total > 0 ? `执行复盘：${rateLabel} 完成` : '执行复盘待开始',
    subtitle: total > 0
      ? `过去 ${review?.window_days ?? 7} 天完成 ${completed}/${total} 个行动。`
      : '先完成今天最重要的一件事，复盘会开始累积。',
    route: '/my-progress',
    items: [
      { key: 'completion_rate', label: '完成率', value: rateLabel, accent: completionRate >= 0.6 },
      { key: 'completed', label: '已完成', value: `${completed}`, accent: completed > 0 },
      { key: 'total', label: '总行动', value: `${total}`, accent: false },
      { key: 'learnable', label: '可学习', value: `${learnable}`, accent: learnable > 0 },
    ],
    highlight: pickMetricHighlight(review?.metrics ?? {}),
  };
}

export async function fetchOperatingReviewSummary(windowDays: 7 | 30 | 90 = 7): Promise<OperatingReviewSummary> {
  const review = await fetchHealthOperatingReview(windowDays);
  return buildOperatingReviewSummary(review);
}

function pickMetricHighlight(metrics: HealthOperatingReview['metrics']): OperatingReviewHighlight | null {
  const candidates = Object.entries(METRIC_META)
    .map(([key, meta], priority) => {
      const change = metrics[key];
      if (!change || change.status !== 'present' || change.delta == null) return null;
      const positive = meta.good === 'down' ? change.delta < 0 : change.delta > 0;
      return {
        key,
        meta,
        delta: change.delta,
        positive,
        priority,
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    .sort((a, b) => {
      if (a.positive !== b.positive) return a.positive ? -1 : 1;
      return a.priority - b.priority;
    });

  const picked = candidates[0];
  if (!picked) return null;

  return {
    label: '最明显变化',
    value: `${picked.meta.label} ${formatSigned(picked.delta)}${picked.meta.unit ? ` ${picked.meta.unit}` : ''}`,
    detail: '时间关联，不等于因果。',
    positive: picked.positive,
  };
}

function clampRate(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function formatSigned(value: number): string {
  if (value > 0) return `+${formatNumber(value)}`;
  return formatNumber(value);
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? `${value}` : `${Number(value.toFixed(1))}`;
}
