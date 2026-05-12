import api from './api';

export interface ProgressCard {
  id: number;
  title: string;
  status: string | null;
  user_decision: string | null;
  outcome: 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;
  effect_size: number | null;
  accuracy_score: number | null;
  metric_key: string | null;
  baseline_value: string | null;
  actual_value: string | null;
  created_at: string | null;
  completed_at: string | null;
  graded_at: string | null;
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

export async function fetchMyProgress(days = 30): Promise<ProgressDashboard> {
  const { data } = await api.get<ProgressDashboard>(
    `/action-cards/me/progress?days=${days}`,
  );
  return data;
}
