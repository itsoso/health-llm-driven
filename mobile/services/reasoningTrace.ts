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
  // Only for decision_type === 'llm_arbitration'
  arbitration_extra?: {
    winning_side: string;
    caveats: string[];
    conflicts_addressed: number;
    specialists_involved: string[];
  };
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

// -------------------------------------------------------------------
// Task 3 (Mobile ExplainSheet): 单条 alert / finding 的 reasoning 详情抽屉
// 对应后端 /reasoning-trace/safety/{audit_id} 和 /reasoning-trace/specialist/{audit_id}
// -------------------------------------------------------------------

export interface ExplainTwinEvidence {
  partition: string;
  field: string;
  value: string | number | boolean;
  source: string;
  freshness_hours: number | null;
}

export interface ExplainRelatedFact {
  id: number;
  tier: string;
  predicate: string;
  preview: string;
  confidence: number | null;
}

export interface ExplainResponse {
  source: 'safety' | 'specialist';
  summary: string;
  // Safety only
  rule?: {
    name: string;
    category: string;
    severity?: number | null;
    threshold?: string | null;
  };
  // Specialist only
  specialist?: string;
  kind?: string;
  data?: Record<string, unknown>;
  proposed_cards_count?: number;

  twin_evidence: ExplainTwinEvidence[];
  related_facts: ExplainRelatedFact[];
  confidence: { twin_field_count: number; memory_fact_count: number };
  confidence_note: string;
  generated_at?: string | null;
}

export async function explainSafety(
  auditId: number,
  ruleId: string,
): Promise<ExplainResponse> {
  const { data } = await api.get<ExplainResponse>(
    `/reasoning-trace/safety/${auditId}`,
    { params: { rule_id: ruleId } },
  );
  return data;
}

export async function explainSpecialist(
  auditId: number,
  specialist: string,
): Promise<ExplainResponse> {
  const { data } = await api.get<ExplainResponse>(
    `/reasoning-trace/specialist/${auditId}`,
    { params: { specialist } },
  );
  return data;
}
