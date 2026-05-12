import api from './api';

export interface DietCard {
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
  created_at: string | null;
  graded_at: string | null;
}

export interface DietPlan {
  has_data: boolean;
  error?: string;
  summary?: string;
  energy?: {
    tdee_kcal: number;
    intake_kcal: number;
    remaining_kcal: number;
    progress_pct: number;
    meals_logged?: number;
  } | null;
  protein?: {
    today_g: number;
    target_g: number;
    progress_pct: number;
  } | null;
  hydration?: {
    ml_today: number;
    goal_ml: number;
    progress_pct: number;
    status: 'low' | 'ok' | 'full';
  } | null;
  next_meal?: {
    slot: string;
    guidance: string;
  } | null;
  supplement?: {
    taken_today: number;
    total: number;
    pending?: string[];
  } | null;
  gene_nudges?: Array<Record<string, any>>;
  labs_concern?: { items: string[] } | null;
  proposed_experiments?: any[];
  related_cards?: DietCard[];
}

export async function fetchDietPlan(): Promise<DietPlan> {
  const { data } = await api.get<DietPlan>('/diet-plan/me');
  return data;
}
