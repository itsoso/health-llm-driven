import api from './api';

export type OutcomeRange = '6m' | '1y' | '2y' | 'all';
export type OutcomeGranularity = 'week' | 'month';

export interface TimelinePoint {
  bucket: string;
  date: string;
  hrv: number | null;
  rhr: number | null;
  sleep_score: number | null;
  deep_sleep_min: number | null;
  body_battery_high: number | null;
  steps: number | null;
  weight_kg: number | null;
  systolic: number | null;
  diastolic: number | null;
  samples: number;
}

export interface TimelineEvent {
  id: string;
  kind: string;
  date: string;
  title: string;
  detail: string | null;
  color: string | null;
}

export interface OutcomeMetric {
  first: number | null;
  last: number | null;
  delta: number | null;
  unit: string;
  desirable: 'up' | 'down' | 'flat';
}

export interface OutcomeTimelineResponse {
  range: OutcomeRange;
  granularity: OutcomeGranularity;
  start_date: string | null;
  end_date: string;
  points: TimelinePoint[];
  events: TimelineEvent[];
  summary: {
    total_days: number;
    covered_days: number;
    metrics: {
      hrv?: OutcomeMetric;
      rhr?: OutcomeMetric;
      weight?: OutcomeMetric;
      sleep_score?: OutcomeMetric;
    };
  };
}

export interface OutcomeReviewMetric {
  key: 'hrv' | 'rhr' | 'sleep_score' | 'weight' | 'bp';
  label: string;
  value: string;
  delta: string | null;
  unit: string;
  desirable: 'up' | 'down' | 'flat';
}

export async function getMyOutcomeTimeline(
  range: OutcomeRange = '6m',
  granularity: OutcomeGranularity = 'month',
): Promise<OutcomeTimelineResponse> {
  const { data } = await api.get<OutcomeTimelineResponse>('/personal-outcome/me/timeline', {
    params: { range, granularity },
  });
  return data;
}

export interface ScorecardCard {
  card_id: number;
  title: string;
  metric: string | null;
  score: number;
  graded_at: string | null;
  specialist: string | null;
}

export interface ScorecardSpecialistRow {
  name: string;
  total: number;
  hits: number;
  hit_rate: number;
  avg_score: number;
}

export interface ScorecardResponse {
  window_days: number;
  overall: {
    total: number;
    high_count: number;
    low_count: number;
    avg_score: number;
    hit_rate: number;
  };
  by_specialist: ScorecardSpecialistRow[];
  top_hits: ScorecardCard[];
  top_misses: ScorecardCard[];
}

export async function getMyScorecard(days = 90, topN = 3): Promise<ScorecardResponse> {
  const { data } = await api.get<ScorecardResponse>('/personal-outcome/me/scorecard', {
    params: { days, top_n: topN },
  });
  return data;
}

export const SPECIALIST_LABEL: Record<string, string> = {
  fuel_strategist: '营养',
  movement_coach: '运动',
  recovery_coach: '恢复',
  safety_guardian: '安全',
  mental_health_companion: '心理',
  hypertension_specialist: '血压',
  metabolic_specialist: '代谢',
  rhinitis_specialist: '鼻炎',
  knowledge_librarian: '知识',
  longitudinal_analyst: '长期趋势',
};

export function specialistLabel(name: string | null): string {
  if (!name) return '未知';
  return SPECIALIST_LABEL[name] || name;
}

function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value == null) return '--';
  return value.toFixed(digits);
}

function metricFromSummary(
  key: OutcomeReviewMetric['key'],
  label: string,
  metric: OutcomeMetric | undefined,
  digits = 0,
): OutcomeReviewMetric {
  return {
    key,
    label,
    value: formatNumber(metric?.last, digits),
    delta: metric?.delta == null ? null : `${metric.delta > 0 ? '+' : ''}${metric.delta.toFixed(digits)}`,
    unit: metric?.unit || '',
    desirable: metric?.desirable || 'flat',
  };
}

function firstAndLastWithBp(points: TimelinePoint[]): { first?: TimelinePoint; last?: TimelinePoint } {
  const valid = points.filter(point => point.systolic != null && point.diastolic != null);
  return { first: valid[0], last: valid[valid.length - 1] };
}

export function buildOutcomeReviewMetrics(timeline: OutcomeTimelineResponse | null | undefined): OutcomeReviewMetric[] {
  if (!timeline) return [];
  const metrics = timeline.summary?.metrics || {};
  const out: OutcomeReviewMetric[] = [
    metricFromSummary('hrv', 'HRV', metrics.hrv, 0),
    metricFromSummary('rhr', '静息心率', metrics.rhr, 0),
    metricFromSummary('sleep_score', '睡眠评分', metrics.sleep_score, 0),
    metricFromSummary('weight', '体重', metrics.weight, 1),
  ];

  const bp = firstAndLastWithBp(timeline.points || []);
  if (bp.last?.systolic != null && bp.last.diastolic != null) {
    const systolicDelta = bp.first?.systolic == null ? null : bp.last.systolic - bp.first.systolic;
    const diastolicDelta = bp.first?.diastolic == null ? null : bp.last.diastolic - bp.first.diastolic;
    out.push({
      key: 'bp',
      label: '血压',
      value: `${Math.round(bp.last.systolic)}/${Math.round(bp.last.diastolic)}`,
      delta: systolicDelta == null || diastolicDelta == null
        ? null
        : `${systolicDelta > 0 ? '+' : ''}${Math.round(systolicDelta)}/${diastolicDelta > 0 ? '+' : ''}${Math.round(diastolicDelta)}`,
      unit: 'mmHg',
      desirable: 'down',
    });
  }

  return out.filter(metric => metric.value !== '--');
}
