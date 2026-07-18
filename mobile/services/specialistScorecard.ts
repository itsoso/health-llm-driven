/**
 * Specialist Scorecard service
 *
 * Task 7: 包装两个已有后端接口:
 * - GET /specialists/{name}/scorecard  (Task 6 新增, commit 0c18df5)
 * - GET /specialists/hit-rate          (已存在, Hero chip 复用)
 */
import api from './api';

// ── 单 specialist 详情 ────────────────────────────────────────

export interface ScorecardCard {
  id: number;
  title: string;
  created_at: string | null;
  graded_at: string | null;
  metric_key: string | null;
  target_value: string | null;
  actual_value: string | null;
  accuracy_score: number | null;
  score_status: 'eligible' | 'clinician_review';
  adherence_kind: string | null;
  adherence_confidence: number | null;
  why_short: string | null;
}

export interface ScorecardResponse {
  specialist: string;
  window_days: number;
  proposed_count: number;
  graded_count: number;
  hit_rate: number | null;
  grading_coverage: number;
  clinical_review_count: number;
  avg_accuracy: number | null;
  cards: ScorecardCard[];
}

export async function fetchScorecard(name: string, days = 30): Promise<ScorecardResponse> {
  const { data } = await api.get<ScorecardResponse>(
    `/specialists/${encodeURIComponent(name)}/scorecard`,
    { params: { days } },
  );
  return data;
}

// ── hit-rate 总览 (for chip row) ──────────────────────────────

export interface HitRateRow {
  specialist: string;
  total_graded: number;
  hit_rate: number;
  avg_accuracy_score: number;
  hits: number;
  is_significant: boolean;
}

export interface HitRateResponse {
  since: string;
  days: number;
  by_specialist: HitRateRow[];
  pending_grading: number;
  best_specialist: string | null;
}

export async function fetchHitRate(days = 30): Promise<HitRateResponse> {
  const { data } = await api.get<HitRateResponse>('/specialists/hit-rate', {
    params: { days },
  });
  return data;
}
