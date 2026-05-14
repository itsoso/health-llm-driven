import api from './api';

export type TrajectoryRiskLevel = 'high' | 'attention' | 'unknown' | 'ok' | string;

export interface TrajectoryRisk {
  domain: string;
  level: TrajectoryRiskLevel;
  title: string;
  why?: string | null;
  signals?: string[];
  primary_action?: string | null;
}

export interface TrajectoryDataGap {
  code: string;
  label: string;
  next_step?: string | null;
}

export interface HealthTrajectorySnapshot {
  user_id?: number;
  generated_at: string;
  horizon?: string;
  focus_domains: string[];
  congenital_baseline?: Record<string, unknown>;
  epigenetic_feedback?: Record<string, unknown>;
  clinical_anchors?: Record<string, unknown>;
  realtime_state?: Record<string, unknown>;
  modifiable_levers?: Record<string, unknown>;
  trajectory_risks: TrajectoryRisk[];
  next_actions?: Record<string, unknown>[];
  doctor_escalation?: Record<string, unknown>;
  data_gaps: TrajectoryDataGap[];
  safety_boundary?: string;
}

const RISK_ORDER: Record<string, number> = {
  high: 0,
  attention: 1,
  unknown: 2,
  ok: 3,
};

export async function getHealthTrajectory(): Promise<HealthTrajectorySnapshot> {
  const { data } = await api.get<HealthTrajectorySnapshot>('/trajectory/me');
  return {
    ...data,
    focus_domains: Array.isArray(data.focus_domains) ? data.focus_domains : [],
    trajectory_risks: Array.isArray(data.trajectory_risks) ? data.trajectory_risks : [],
    data_gaps: Array.isArray(data.data_gaps) ? data.data_gaps : [],
  };
}

export function pickPrimaryTrajectoryRisks(risks: TrajectoryRisk[] = [], limit = 3): TrajectoryRisk[] {
  return [...risks]
    .filter(risk => Boolean(risk?.title))
    .sort((a, b) => (RISK_ORDER[a.level] ?? 9) - (RISK_ORDER[b.level] ?? 9))
    .slice(0, limit);
}
