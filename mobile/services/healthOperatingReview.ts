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

export interface HealthOperatingReview {
  window_days: ReviewWindowDays;
  start_date: string;
  end_date: string;
  execution: ExecutionSummary;
  metrics: Record<string, MetricChange>;
  completed_action_keys: string[];
  prediction_backtest?: PredictionBacktestPlaceholder;
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
