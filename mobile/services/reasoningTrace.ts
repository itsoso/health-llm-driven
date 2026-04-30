import api from './api';

export interface TraceEvidence {
  metric: string | null;
  current: number | null;
  baseline: number | null;
  threshold: number | null;
  deviation_pct: number | null;
}

export interface TraceRule {
  id: string;
  engine: string;
  category: string;
}

export interface TraceOutcome {
  kind: string;
  id: number;
  title: string;
  status: string;
  check_back_date: string | null;
  metric_key: string | null;
}

export interface TraceMemoryFact {
  id: number;
  tier: string;
  subject: string;
  predicate: string;
  object_value: string;
  object_unit: string | null;
  confidence: number;
  created_at?: string;
}

export interface ReasoningTrace {
  id: string;
  timestamp: string | null;
  decision_type: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  message: string;
  rule: TraceRule;
  evidence: TraceEvidence;
  confidence: number;
  is_suppressed: boolean;
  notification_sent: boolean;
  outcome: TraceOutcome | null;
  related_memory: TraceMemoryFact[];
}

export interface TraceListResponse {
  traces: ReasoningTrace[];
  summary: {
    total: number;
    by_type: Record<string, number>;
    by_severity: Record<string, number>;
    window_days: number;
  };
}

export async function listRecentTraces(params?: {
  days?: number;
  limit?: number;
  decision_type?: string;
  include_suppressed?: boolean;
}): Promise<TraceListResponse> {
  const { data } = await api.get<TraceListResponse>('/reasoning-trace/recent', {
    params: params ?? {},
  });
  return data;
}

export async function getTraceDetail(traceId: string): Promise<ReasoningTrace> {
  const { data } = await api.get<ReasoningTrace>(`/reasoning-trace/${traceId}`);
  return data;
}
