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
  action_key?: string | null;
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

export type DailyPlanActionFeedbackStatus = 'accepted' | 'adjusted' | 'done' | 'skipped' | 'failed';
export type DailyPlanActionEventType =
  | 'suggested'
  | 'accepted'
  | 'adjusted'
  | 'completed'
  | 'skipped'
  | 'verified';

export interface DailyPlanActionFeedbackResult {
  id: number;
  plan_id?: number | null;
  plan_date: string;
  action_key: string;
  action_title: string;
  status: DailyPlanActionFeedbackStatus | string;
  reason?: string | null;
  source: string;
}

export interface DailyPlanActionEventRequest {
  event_type: DailyPlanActionEventType;
  payload?: Record<string, unknown>;
  plan_date?: string;
}

export interface DailyPlanActionEventResult {
  id: number;
  plan_id?: number | null;
  plan_date: string;
  action_id: string;
  action_title: string;
  event_type: DailyPlanActionEventType | string;
  action_state: DailyPlanActionEventType | string;
  payload: Record<string, unknown>;
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

export async function submitDailyPlanActionFeedback(
  actionKey: string,
  status: DailyPlanActionFeedbackStatus,
  reason?: string,
): Promise<DailyPlanActionFeedbackResult> {
  const body = reason?.trim()
    ? { status, reason: reason.trim() }
    : { status };
  const { data } = await api.post<DailyPlanActionFeedbackResult>(
    `/daily-plan/me/actions/${encodeURIComponent(actionKey)}/feedback`,
    body,
  );
  return data;
}

export async function recordDailyPlanActionEvent(
  actionId: string,
  request: DailyPlanActionEventRequest,
): Promise<DailyPlanActionEventResult> {
  const body = {
    event_type: request.event_type,
    payload: request.payload ?? {},
    ...(request.plan_date ? { plan_date: request.plan_date } : {}),
  };
  const { data } = await api.post<DailyPlanActionEventResult>(
    `/daily-plan/actions/${encodeURIComponent(actionId)}/events`,
    body,
  );
  return {
    ...data,
    action_state: data.action_state || data.event_type,
    payload: data.payload ?? {},
  };
}
