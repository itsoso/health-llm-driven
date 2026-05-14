import api from './api';

export type DailyPlanDomain =
  | 'measurement'
  | 'nutrition'
  | 'movement'
  | 'sleep'
  | 'intervention'
  | 'doctor'
  | string;
export type DailyPlanEvidenceTier =
  | 'clinical_guideline'
  | 'strong_behavioral'
  | 'wearable_proxy'
  | 'genetic_association'
  | 'experimental'
  | string;
export type DailyPlanConfidence = 'high' | 'medium' | 'low' | string;

export interface DailyPlanAction {
  domain: DailyPlanDomain;
  title: string;
  why?: string | null;
  when?: string | null;
  metric_key?: string | null;
  target_value?: string | null;
  evidence_level?: 'high' | 'medium' | 'low' | 'medical_grade' | string | null;
  evidence_tier?: DailyPlanEvidenceTier | null;
  confidence?: DailyPlanConfidence | null;
  claim_boundary?: string | null;
  source_card_id?: number | null;
  check_back_date?: string | null;
}

export interface DailyOperatingPlan {
  id?: number | null;
  user_id?: number;
  plan_date: string;
  primary_goal: string;
  status: 'draft' | 'active' | 'completed' | 'archived' | string;
  state_summary: Record<string, unknown>;
  actions: DailyPlanAction[];
  nutrition_targets?: Record<string, unknown>;
  movement_targets?: Record<string, unknown>;
  sleep_targets?: Record<string, unknown>;
  measurements?: Record<string, unknown>;
  doctor_escalation?: {
    needed?: boolean;
    reason?: string | null;
    suggested_specialty?: string | null;
  } | null;
  verification?: {
    window_days?: number;
    metrics?: string[];
    check_back_date?: string | null;
  };
}

export async function getDailyOperatingPlan(): Promise<DailyOperatingPlan> {
  const { data } = await api.get<DailyOperatingPlan>('/daily-plan/me');
  return {
    ...data,
    actions: Array.isArray(data.actions) ? data.actions : [],
    state_summary: data.state_summary ?? {},
  };
}

export function pickTopPlanActions(actions: DailyPlanAction[] = [], limit = 3): DailyPlanAction[] {
  return actions
    .filter(action => Boolean(action?.title))
    .slice(0, limit);
}
