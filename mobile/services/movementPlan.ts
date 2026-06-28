import api from './api';

export interface MovementCard {
  id: number;
  title: string;
  status: string | null;
  user_decision: string | null;
  outcome: 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;
  effect_size: number | null;
  metric_key: string | null;
  baseline_value: string | null;
  actual_value: string | null;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  evidence_refs?: (string | { claim_id?: string; doc_id?: string; id?: string })[] | null;
  created_at: string | null;
  graded_at: string | null;
}

export interface MovementPlan {
  has_data: boolean;
  error?: string;
  summary?: string;
  training_status?: {
    status: string;
    status_zh: string;
    source?: string;
    acwr?: number | null;
    garmin_load_ratio?: number | null;
    garmin_acute_load?: number | null;
    training_load_7d?: number | null;
    workouts_this_week?: number | null;
    garmin_feedback?: string | null;
  };
  today?: {
    intensity: string;
    intensity_zh: string;
    guidance: string;
    based_on_readiness?: string | null;
  };
  fitness?: {
    vo2max_running?: number | null;
    vo2max_cycling?: number | null;
    resting_hr?: number | null;
  } | null;
  gene_biases?: Array<Record<string, any>>;
  week_adjustment?: string | null;
  recent_workouts?: {
    count: number;
    workouts: any[];
    avg_perceived_exertion?: number | null;
    high_intensity_minutes_7d?: number;
  } | null;
  proposed_experiments?: any[];
  related_cards?: MovementCard[];
}

export async function fetchMovementPlan(): Promise<MovementPlan> {
  const { data } = await api.get<MovementPlan>('/movement/plan/me');
  return data;
}
