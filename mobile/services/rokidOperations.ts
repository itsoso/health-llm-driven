import api from './api';

export type RokidOperationStatus =
  | 'queued'
  | 'started'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'completed'
  | string;

export type CreateRokidOperationInput = {
  operationId?: string;
  type?: string;
  capability?: string;
  status?: RokidOperationStatus;
  state?: RokidOperationStatus;
  sourceDevice?: string;
  primarySurface?: string;
  summary?: string;
  lastErrorCode?: string;
  meta?: Record<string, unknown>;
  entityRefs?: Record<string, unknown>;
  writeIntentId?: number;
};

export type RokidOperation = {
  id: number;
  operation_id: string;
  user_id: number;
  type: string;
  state: RokidOperationStatus;
  primary_surface: string;
  summary?: string | null;
  last_error_code?: string | null;
  meta?: Record<string, unknown> | null;
  entity_refs?: Record<string, unknown> | null;
  write_intent_id?: number | null;
  started_at: string;
  finished_at?: string | null;
  created_at: string;
};

export type AppendRokidOperationEventInput = {
  eventType: string;
  phase?: string;
  severity?: 'info' | 'pass' | 'warn' | 'block' | 'error' | string;
  status?: RokidOperationStatus;
  state?: RokidOperationStatus;
  message?: string;
  payload?: Record<string, unknown>;
  occurredAt?: string;
};

export type RokidOperationEvent = {
  id: number;
  operation_id: string;
  user_id: number;
  event_type: string;
  phase?: string | null;
  severity: string;
  message?: string | null;
  payload?: Record<string, unknown> | null;
  occurred_at: string;
  created_at: string;
};

export type RokidOperationTimeline = {
  operation: RokidOperation;
  events: RokidOperationEvent[];
};

export type UploadRokidDiagnosticsInput = {
  operationId: string;
  summary: string;
  diagnostics: Record<string, unknown>;
  severity?: 'info' | 'pass' | 'warn' | 'block' | 'error' | string;
  occurredAt?: string;
};

export function createRokidOperationId(prefix = 'op'): string {
  const safePrefix = prefix.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-') || 'op';
  const suffix = Math.random().toString(36).slice(2, 8).padEnd(6, '0');
  return `rokid-${safePrefix}-${Date.now()}-${suffix}`;
}

export async function createRokidOperation(input: CreateRokidOperationInput): Promise<RokidOperation> {
  const response = await api.post<RokidOperation>('/devices/rokid/operations', {
    operation_id: input.operationId,
    type: input.type ?? input.capability,
    state: input.state ?? input.status ?? 'queued',
    primary_surface: input.primarySurface ?? input.sourceDevice ?? 'rokid_glasses',
    summary: input.summary,
    last_error_code: input.lastErrorCode,
    meta: input.meta,
    entity_refs: input.entityRefs,
    write_intent_id: input.writeIntentId,
  });
  return response.data;
}

export async function appendRokidOperationEvent(
  operationId: string,
  input: AppendRokidOperationEventInput,
): Promise<RokidOperationEvent> {
  const response = await api.post<RokidOperationEvent>(
    `/devices/rokid/operations/${encodeURIComponent(operationId)}/events`,
    {
      event_type: input.eventType,
      phase: input.phase,
      severity: input.severity ?? 'info',
      state: input.state ?? input.status,
      message: input.message,
      payload: input.payload,
      occurred_at: input.occurredAt,
    },
  );
  return response.data;
}

export async function uploadRokidDiagnostics(input: UploadRokidDiagnosticsInput): Promise<RokidOperationEvent> {
  const response = await api.post<RokidOperationEvent>('/devices/rokid/diagnostics', {
    operation_id: input.operationId,
    summary: input.summary,
    diagnostics: input.diagnostics,
    severity: input.severity ?? 'warn',
    occurred_at: input.occurredAt,
  });
  return response.data;
}

export async function getRokidOperationTimeline(operationId: string): Promise<RokidOperationTimeline> {
  const response = await api.get<RokidOperationTimeline>(
    `/devices/rokid/operations/${encodeURIComponent(operationId)}`,
  );
  return response.data;
}
