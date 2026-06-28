import api from './api';

export type ReviewWindowDays = 7 | 30 | 90;

export interface ExecutionSummary {
  total_events: number;
  completed_events: number;
  completion_rate: number;
  by_status: Record<string, number>;
  by_domain: Record<string, number>;
}

export interface MetricChange {
  status: 'present' | 'missing';
  count: number;
  first?: number;
  first_date?: string;
  current: number | null;
  current_date?: string;
  delta: number | null;
}

export interface PredictionBacktestPlaceholder {
  version: string;
  status: 'not_ready' | 'ready' | string;
  reason: string;
  candidate_count: number;
  ready_candidate_count: number;
  window_days: ReviewWindowDays;
  minimum_window_days: number;
  completed_action_count: number;
  eligible_metrics: string[];
  requirements: string[];
  boundary: string;
  summary?: { met: number; not_met: number; inconclusive: number };
  confidence_summary?: { high: number; medium: number; low: number };
  results?: PredictionBacktestResult[];
}

export interface PredictionBacktestResult {
  prediction_id: string;
  source?: string | null;
  action_key: string;
  action_title: string;
  metric: string;
  horizon_days?: number | null;
  baseline?: number | string | null;
  baseline_date?: string | null;
  expected_signal?: Record<string, unknown>;
  actual_result?: { current?: number | string | null; current_date?: string | null };
  observed_delta?: number | null;
  verdict: 'met' | 'not_met' | 'inconclusive' | string;
  downgrade_reason?: string | null;
  confidence_before?: string | null;
  confidence_after?: string | null;
  explanation?: string | null;
  attribution?: string | null;
  boundary?: string | null;
}

export type PredictionTimelineEventType =
  | 'prediction_created'
  | 'action_executed'
  | 'outcome_observed'
  | 'review_verdict';

export interface PredictionTimelineItem {
  id: string;
  prediction_id: string;
  event_type: PredictionTimelineEventType | string;
  occurred_at: string;
  title: string;
  summary: string;
  metric: string;
  status: string;
  confidence?: string | null;
  boundary?: string | null;
}

export interface CausalMemoryNote {
  metric: string;
  before?: number | null;
  after?: number | null;
  pct?: number | null;
  direction?: string | null;
  text: string;
}

export interface CausalMemoryReview {
  notes: CausalMemoryNote[];
  evidence_tier: 'observational' | string;
  claim_boundary: string;
}

export interface HealthOperatingReview {
  window_days: ReviewWindowDays;
  start_date: string;
  end_date: string;
  execution: ExecutionSummary;
  metrics: Record<string, MetricChange>;
  completed_action_keys: string[];
  prediction_backtest?: PredictionBacktestPlaceholder;
  prediction_timeline?: PredictionTimelineItem[];
  causal_memory?: CausalMemoryReview;
}

export async function fetchHealthOperatingReview(
  windowDays: ReviewWindowDays,
): Promise<HealthOperatingReview> {
  const { data } = await api.get<HealthOperatingReview>('/daily-plan/review', {
    params: { window_days: windowDays },
  });
  return data;
}

export function predictionBacktestSummary(backtest?: PredictionBacktestPlaceholder | null): string | null {
  if (!backtest || backtest.status !== 'ready') return null;
  const total = backtest.ready_candidate_count || backtest.results?.length || 0;
  if (total <= 0) return null;
  const met = backtest.summary?.met ?? backtest.results?.filter((r) => r.verdict === 'met').length ?? 0;
  return `预测回测: ${met}/${total} 支持继续当前策略 · 观察性,非因果`;
}

export function predictionTimelineSummary(timeline?: PredictionTimelineItem[] | null): string | null {
  if (!timeline?.length) return null;
  const labels: Record<string, string> = {
    prediction_created: '预测',
    action_executed: '执行',
    outcome_observed: '实际',
    review_verdict: '复盘',
  };
  const seen = new Set<string>();
  const ordered = timeline
    .map(item => labels[item.event_type] ?? item.event_type)
    .filter((label) => {
      if (!label || seen.has(label)) return false;
      seen.add(label);
      return true;
    });
  if (!ordered.length) return null;
  return `预测时间线: ${ordered.join(' -> ')} · 观察性,非因果`;
}

export function causalMemorySummary(memory?: CausalMemoryReview | null): string | null {
  const firstNote = memory?.notes?.find((note) => note.text)?.text;
  if (!firstNote) return null;
  return `个人规律: ${firstNote}`;
}
