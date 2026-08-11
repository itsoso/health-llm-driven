import { completeAgendaItem, type AgendaSkipReason, type AgendaSource, type TrajectoryContext } from './agenda';
import api from './api';
import { recordDailyPlanActionEvent } from './dailyPlan';

export type DailyArtifactEventType = 'impression' | 'accepted' | 'completed' | 'skipped';
export type DailyArtifactTone = 'neutral' | 'steady' | 'focused' | 'urgent' | string;
export type DailyArtifactConfidence = 'low' | 'medium' | 'high' | string;

export interface DailyArtifactState {
  label: string;
  tone: DailyArtifactTone;
  summary: string;
}

export interface DailyArtifactEvidence {
  kind: string;
  label: string;
  summary: string;
  source?: string | null;
  domain?: string | null;
  level?: string | null;
  confidence?: string | number | null;
  metrics?: string[] | null;
  window_days?: number | null;
}

export interface DailyArtifactTopAction {
  id: string;
  title: string;
  type?: string | null;
  status?: string | null;
  priority_tier?: string | null;
  confidence?: DailyArtifactConfidence | null;
  source?: {
    object_type?: string | null;
    object_id?: number | string | null;
    slot?: string | null;
  } | null;
  why_now?: string | null;
  do_now?: string | null;
  verify_by?: Record<string, unknown> | null;
  trajectory_context?: TrajectoryContext | null;
  target_state_variable?: string | null;
  verification_signal?: string | null;
  claim_boundary?: string | null;
  runtime_context?: Record<string, unknown> | null;
  actions?: {
    complete?: {
      method?: string | null;
      endpoint?: string | null;
      enabled?: boolean;
      source?: DailyArtifactTopAction['source'];
      payload?: Record<string, unknown> | null;
    } | null;
    skip?: {
      requires_reason?: boolean;
      event_type?: string;
    } | null;
    ask_reva?: {
      target?: string | null;
    } | null;
  } | null;
}

export interface DailyArtifact {
  artifact_date: string;
  generated_by?: string | null;
  source?: Record<string, unknown> | null;
  empty_state: boolean;
  state: DailyArtifactState;
  top_action: DailyArtifactTopAction | null;
  evidence: DailyArtifactEvidence[];
  confidence: DailyArtifactConfidence;
  freshness: {
    status?: string | null;
    sources?: string[];
  };
  safety_boundary: string;
}

export type DailyArtifactCompletionTarget =
  | { kind: 'agenda'; source: AgendaSource }
  | { kind: 'daily_plan_action'; actionId: string };

const AGENDA_COMPLETION_SOURCE_TYPES = new Set(['health_protocol', 'medication', 'supplement']);
const DAILY_PLAN_ACTION_ID_RE = /^[A-Za-z0-9._:-]+$/;
const FOLLOW_UP_ACTION_WORDS = ['复查', '检查', '化验', '随访'];

/**
 * Resolve the actual write path for a Daily Artifact action.
 *
 * The backend may be older than the client and still advertise `enabled=true`
 * for read-only projections such as HealthProblem follow-ups. Keep this client
 * gate aligned with the real endpoints so a visible completion button never
 * dispatches a request that is guaranteed to fail.
 */
export function resolveDailyArtifactCompletionTarget(
  action: DailyArtifactTopAction | null | undefined,
): DailyArtifactCompletionTarget | null {
  const source = action?.actions?.complete?.source ?? action?.source;
  const objectType = source?.object_type?.trim();
  const objectId = source?.object_id;
  if (!objectType || objectId == null) return null;

  if (objectType === 'daily_plan_action') {
    const actionId = String(objectId).trim();
    if (!actionId || actionId.length > 160 || !DAILY_PLAN_ACTION_ID_RE.test(actionId)) return null;
    return { kind: 'daily_plan_action', actionId };
  }

  if (!AGENDA_COMPLETION_SOURCE_TYPES.has(objectType)) return null;
  if (!isPositiveNumericId(objectId)) return null;
  return {
    kind: 'agenda',
    source: {
      object_type: objectType,
      object_id: objectId,
      ...(source?.slot ? { slot: source.slot } : {}),
    },
  };
}

export async function completeDailyArtifactAction(
  action: DailyArtifactTopAction,
  artifactDate: string,
): Promise<unknown> {
  const target = resolveDailyArtifactCompletionTarget(action);
  if (!target) throw new Error('daily_artifact_completion_not_supported');

  if (target.kind === 'daily_plan_action') {
    return recordDailyPlanActionEvent(target.actionId, {
      event_type: 'completed',
      plan_date: artifactDate,
      payload: { source: 'daily_artifact' },
    });
  }
  return completeAgendaItem(target.source, 'protocol');
}

export function isDailyArtifactFollowUpAction(
  action: DailyArtifactTopAction | null | undefined,
): boolean {
  const sourceType = action?.actions?.complete?.source?.object_type ?? action?.source?.object_type;
  const text = `${action?.title ?? ''} ${action?.do_now ?? ''}`;
  return action?.type === 'checkup'
    || sourceType === 'review_schedule'
    || (sourceType === 'health_problem' && FOLLOW_UP_ACTION_WORDS.some((word) => text.includes(word)));
}

function isPositiveNumericId(value: number | string): boolean {
  if (typeof value === 'number') return Number.isInteger(value) && value > 0;
  return /^\d+$/.test(value.trim()) && Number(value) > 0;
}

export interface DailyArtifactEventRequest {
  eventType: DailyArtifactEventType;
  artifactDate?: string | null;
  topActionId?: string | null;
  skipReason?: AgendaSkipReason | string | null;
  deliveredContext?: Record<string, unknown> | null;
}

export interface DailyArtifactEventResult {
  id: number;
  user_id?: number;
  artifact_date?: string;
  event_type: DailyArtifactEventType | string;
  top_action_id?: string | null;
  skip_reason?: string | null;
  delivered_context?: Record<string, unknown> | null;
  week_index?: number;
  created_at?: string | null;
}

export interface DailyArtifactDetailOptions {
  date?: string | null;
  actionId?: string | null;
  followupWithinDays?: number;
}

const DEFAULT_STATE: DailyArtifactState = {
  label: '今日状态',
  tone: 'neutral',
  summary: '今天暂无需要突出的健康行动。',
};

export async function getDailyArtifact(followupWithinDays = 7): Promise<DailyArtifact> {
  const { data } = await api.get<Partial<DailyArtifact>>('/daily-artifact/me', {
    params: { followup_within_days: followupWithinDays },
  });
  return normalizeDailyArtifact(data);
}

export async function getDailyArtifactDetail(
  options: DailyArtifactDetailOptions = {},
): Promise<DailyArtifact | null> {
  const params: Record<string, string | number> = {};
  if (options.date) params.artifact_date = options.date;
  params.followup_within_days = options.followupWithinDays ?? 7;
  if (options.actionId) params.top_action_id = options.actionId;

  const { data } = await api.get<Partial<DailyArtifact>>('/daily-artifact/me', { params });
  const artifact = normalizeDailyArtifact(data);
  if (options.date && artifact.artifact_date !== options.date) return null;
  if (options.actionId && artifact.top_action?.id !== options.actionId) return null;
  return artifact;
}

export async function recordDailyArtifactEvent(
  request: DailyArtifactEventRequest,
): Promise<DailyArtifactEventResult> {
  if (request.eventType === 'skipped' && !request.skipReason) {
    throw new Error('skipReason is required for skipped Daily Artifact events');
  }

  const body = {
    event_type: request.eventType,
    ...(request.artifactDate ? { artifact_date: request.artifactDate } : {}),
    ...(request.topActionId ? { top_action_id: request.topActionId } : {}),
    ...(request.skipReason ? { skip_reason: request.skipReason } : {}),
    ...(request.deliveredContext ? { delivered_context: request.deliveredContext } : {}),
  };
  const { data } = await api.post<DailyArtifactEventResult>('/daily-artifact/me/events', body);
  return data;
}

export function normalizeDailyArtifact(raw: Partial<DailyArtifact> | null | undefined): DailyArtifact {
  return {
    artifact_date: typeof raw?.artifact_date === 'string' ? raw.artifact_date : todayIsoDate(),
    generated_by: raw?.generated_by ?? null,
    source: raw?.source ?? null,
    empty_state: Boolean(raw?.empty_state),
    state: normalizeState(raw?.state),
    top_action: normalizeTopAction(raw?.top_action),
    evidence: Array.isArray(raw?.evidence)
      ? raw.evidence.filter(Boolean).slice(0, 3).map(normalizeEvidence)
      : [],
    confidence: raw?.confidence || 'low',
    freshness: {
      status: raw?.freshness?.status ?? 'limited',
      sources: Array.isArray(raw?.freshness?.sources) ? raw.freshness.sources : [],
    },
    safety_boundary: raw?.safety_boundary || '这是健康管理行动建议,不替代医生诊断、处方或治疗。',
  };
}

function normalizeState(raw: Partial<DailyArtifactState> | null | undefined): DailyArtifactState {
  return {
    label: raw?.label || DEFAULT_STATE.label,
    tone: raw?.tone || DEFAULT_STATE.tone,
    summary: raw?.summary || DEFAULT_STATE.summary,
  };
}

function normalizeTopAction(
  raw: Partial<DailyArtifactTopAction> | null | undefined,
): DailyArtifactTopAction | null {
  if (!raw || !raw.title) return null;
  return {
    id: String(raw.id || raw.title),
    title: raw.title,
    type: raw.type ?? null,
    status: raw.status ?? 'pending',
    priority_tier: raw.priority_tier ?? null,
    confidence: raw.confidence ?? null,
    source: raw.source ?? null,
    why_now: raw.why_now ?? null,
    do_now: raw.do_now ?? null,
    verify_by: raw.verify_by ?? null,
    trajectory_context: raw.trajectory_context ?? null,
    target_state_variable: raw.target_state_variable ?? null,
    verification_signal: raw.verification_signal ?? null,
    claim_boundary: raw.claim_boundary ?? null,
    runtime_context: raw.runtime_context ?? null,
    actions: raw.actions ?? null,
  };
}

function normalizeEvidence(raw: Partial<DailyArtifactEvidence>): DailyArtifactEvidence {
  return {
    kind: raw.kind || 'evidence',
    label: raw.label || 'Evidence',
    summary: raw.summary || '当前证据不足,请以实际状态为准。',
    source: raw.source ?? null,
    domain: raw.domain ?? null,
    level: raw.level ?? null,
    confidence: raw.confidence ?? null,
    metrics: Array.isArray(raw.metrics) ? raw.metrics : null,
    window_days: typeof raw.window_days === 'number' ? raw.window_days : null,
  };
}

function todayIsoDate(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}
