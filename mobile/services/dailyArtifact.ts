import type { AgendaSkipReason } from './agenda';
import api from './api';

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
  actions?: {
    complete?: {
      enabled?: boolean;
      source?: DailyArtifactTopAction['source'];
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

const DEFAULT_STATE: DailyArtifactState = {
  label: '今日状态',
  tone: 'neutral',
  summary: '今天暂无需要突出的健康行动。',
};

export async function getDailyArtifact(followupWithinDays = 14): Promise<DailyArtifact> {
  const { data } = await api.get<Partial<DailyArtifact>>('/daily-artifact/me', {
    params: { followup_within_days: followupWithinDays },
  });
  return normalizeDailyArtifact(data);
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
