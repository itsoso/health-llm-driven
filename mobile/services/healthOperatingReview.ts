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
  status: 'not_ready' | string;
  reason: string;
  candidate_count: number;
  ready_candidate_count: number;
  window_days: ReviewWindowDays;
  minimum_window_days: number;
  completed_action_count: number;
  eligible_metrics: string[];
  requirements: string[];
  boundary: string;
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
