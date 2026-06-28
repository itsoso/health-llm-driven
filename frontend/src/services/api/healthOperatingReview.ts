import { api } from './client';

export type ReviewWindowDays = 7 | 30 | 90;

export interface PredictionBacktestResult {
  prediction_id: string;
  action_key: string;
  action_title: string;
  metric: string;
  verdict: string;
  observed_delta?: number | null;
  confidence_before?: string | null;
  confidence_after?: string | null;
  confidence_change?: { before?: string | null; after?: string | null; direction?: string | null };
  inconclusive_reason?: string | null;
  next_step?: {
    action: string;
    label: string;
    reason: string;
    replan_hint?: string | null;
    requires_clinician?: boolean | null;
  } | null;
  boundary?: string | null;
}

export interface PredictionBacktest {
  status: string;
  ready_candidate_count: number;
  summary?: { met?: number; not_met?: number; inconclusive?: number };
  results?: PredictionBacktestResult[];
  boundary?: string | null;
}

export interface HealthOperatingReview {
  window_days: ReviewWindowDays;
  start_date: string;
  end_date: string;
  execution: {
    total_events: number;
    completed_events: number;
    completion_rate: number;
  };
  prediction_backtest?: PredictionBacktest;
}

export async function fetchHealthOperatingReview(windowDays: ReviewWindowDays): Promise<HealthOperatingReview> {
  const response = await api.get<HealthOperatingReview>('/daily-plan/review', {
    params: { window_days: windowDays },
  });
  return response.data;
}

export function predictionNextStepSummary(result?: PredictionBacktestResult | null): string | null {
  const label = result?.next_step?.label;
  if (!result || !label) return null;
  const before = result.confidence_change?.before ?? result.confidence_before;
  const after = result.confidence_change?.after ?? result.confidence_after;
  const confidence = before && after ? ` · 置信度 ${before} → ${after}` : '';
  return `下一步: ${label}${confidence} · 观察性,非因果`;
}
