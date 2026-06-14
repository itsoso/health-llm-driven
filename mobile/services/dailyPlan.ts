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
  cycle_id?: number | null;
  cycle_type?: string | null;
  evidence_refs?: (string | { claim_id?: string; doc_id?: string; id?: string })[] | null;
  verification?: {
    metric?: string | null;
    window_days?: number | null;
    expected_direction?: string | null;
    check_back_date?: string | null;
    cycle_id?: number | null;
    cycle_type?: string | null;
    cycle_target_metric?: string | null;
    cycle_target_metric_label?: string | null;
  } | null;
}

export type DailyPlanActionFeedbackStatus = 'accepted' | 'adjusted' | 'done' | 'skipped' | 'failed';
export type DailyPlanActionEventType =
  | 'suggested'
  | 'accepted'
  | 'adjusted'
  | 'completed'
  | 'skipped'
  | 'verified';

export type DailyPlanActionEventState = DailyPlanActionEventType | 'sending' | 'error';

export interface DailyPlanActionProgress {
  completed_count?: number;
  handled_count?: number;
  remaining_count?: number;
  completed_action_keys?: string[];
  terminal_action_keys?: string[];
}

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
  measurement_automation?: Record<string, unknown>;
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

const COMPLETED_EVENT_STATES = new Set<DailyPlanActionEventType>(['completed', 'verified']);
const TERMINAL_EVENT_STATES = new Set<DailyPlanActionEventType>(['completed', 'skipped', 'verified']);

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function readDailyPlanActionProgress(state: Record<string, unknown>): DailyPlanActionProgress | null {
  const raw = state.action_progress;
  if (!raw || typeof raw !== 'object') return null;
  const progress = raw as Record<string, unknown>;
  return {
    completed_count: numberValue(progress.completed_count) ?? undefined,
    handled_count: numberValue(progress.handled_count) ?? undefined,
    remaining_count: numberValue(progress.remaining_count) ?? undefined,
    completed_action_keys: stringArray(progress.completed_action_keys),
    terminal_action_keys: stringArray(progress.terminal_action_keys),
  };
}

export function buildDailyPlanActionProgressLabel({
  progress,
  actions,
  eventByAction = {},
}: {
  progress: DailyPlanActionProgress | null;
  actions: DailyPlanAction[];
  eventByAction?: Record<string, DailyPlanActionEventState>;
}): string | null {
  if (!progress && actions.length === 0) return null;
  const remoteCompleted = new Set(progress?.completed_action_keys ?? []);
  const remoteTerminal = new Set(progress?.terminal_action_keys ?? []);
  const completed = new Set(remoteCompleted);
  const terminal = new Set(remoteTerminal);

  for (const [actionKey, state] of Object.entries(eventByAction)) {
    if (state === 'sending' || state === 'error') continue;
    if (COMPLETED_EVENT_STATES.has(state)) completed.add(actionKey);
    if (TERMINAL_EVENT_STATES.has(state)) terminal.add(actionKey);
  }

  const visibleLocalTerminal = actions.filter((action) => {
    const key = action.action_key ? String(action.action_key) : '';
    return key && terminal.has(key) && !remoteTerminal.has(key);
  }).length;
  const baseRemaining = progress?.remaining_count ?? actions.length;
  const remaining = Math.max(0, baseRemaining - visibleLocalTerminal);
  const completedCount = Math.max(progress?.completed_count ?? 0, completed.size);
  const handledCount = Math.max(progress?.handled_count ?? 0, terminal.size);
  const otherHandled = Math.max(0, handledCount - completedCount);
  return otherHandled > 0
    ? `今日闭环 ${completedCount} 完成 · ${otherHandled} 已处理 · ${remaining} 待做`
    : `今日闭环 ${completedCount} 完成 · ${remaining} 待做`;
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
