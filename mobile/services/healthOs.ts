/**
 * Personal Health OS — biomarkers + 干预周期 API client.
 * 后端: app/api/biomarkers.py + app/api/intervention_cycles.py
 */
import api from './api';

export interface BiomarkerObs {
  code: string;
  display: string;
  domain: string | null;
  value: number | null;
  unit: string | null;
  normalized_value: number;
  normalized_unit: string;
  ref_low: number | null;
  ref_high: number | null;
  flag: 'low' | 'normal' | 'high' | 'unknown';
  abnormal: boolean;
  is_risk: boolean;
  confidence: 'high' | 'medium' | 'low';
  observed_at: string | null;
}

export interface OutcomeMetric {
  metric_code: string;
  display: string;
  unit: string | null;
  baseline_value: number | null;
  target_value: number | null;
  latest_value: number | null;
  delta: number | null;
  delta_pct: number | null;
  direction: 'down' | 'up';
  status: 'pending' | 'improving' | 'worsening' | 'flat' | 'met';
}

export interface InterventionCycle {
  id: number;
  cycle_type: string;
  status: 'active' | 'completed' | 'abandoned';
  start_date: string | null;
  planned_end_date: string | null;
  baseline_snapshot_id: number | null;
  latest_snapshot_id: number | null;
  target_metrics: Array<{ code: string; target?: number; direction?: string }> | null;
  stop_conditions: string[] | null;
  outcomes: OutcomeMetric[];
}

export interface MetabolicProfile {
  risk: any;
  biomarkers: BiomarkerObs[];
  abnormal: BiomarkerObs[];
  abnormal_count: number;
}

export async function getMetabolicProfile(): Promise<MetabolicProfile> {
  const { data } = await api.get('/biomarkers/me/profile');
  return data;
}

export async function getBiomarkers(): Promise<{ observations: BiomarkerObs[]; abnormal_count: number }> {
  const { data } = await api.get('/biomarkers/me');
  return data;
}

export async function getActiveCycle(): Promise<InterventionCycle | null> {
  const { data } = await api.get('/intervention-cycles/active');
  return data.cycle ?? null;
}

export async function startCycle(days = 90): Promise<{ created: boolean; cycle: InterventionCycle }> {
  const { data } = await api.post('/intervention-cycles', { days });
  return data;
}

export async function recheckCycle(cycleId: number): Promise<InterventionCycle> {
  const { data } = await api.post(`/intervention-cycles/${cycleId}/recheck`);
  return data.cycle;
}

// 干预效应估计 (N-of-1)。后端 app/api/personal_models.py GET /personal-models/treatment-effect。
// 注意: 该端点尚未进 api.generated.ts(契约漂移待补 CI 闸),此处手写镜像后端 schema;
// 前端只渲染 display_label / message(强制 hedge),绝不渲染裸 verdict。
export interface TreatmentEffectItem {
  metric_code: string;
  unit: string | null;
  observed_delta: number | null;
  posterior_effect: number | null;
  ci_low: number | null;
  ci_high: number | null;
  ci_level: number;
  confidence: string;
  verdict: string;       // 仅内部逻辑,前端不直接展示
  display_label: string; // 合规措辞,直显
  evidence_tier: string;
  requires_clinician: boolean;
  message: string;
  model_version: string;
}

export interface TreatmentEffectResponse {
  estimates: TreatmentEffectItem[];
}

export async function getTreatmentEffect(cycleId: number): Promise<TreatmentEffectResponse> {
  const { data } = await api.get('/personal-models/treatment-effect', { params: { cycle_id: cycleId } });
  return data;
}
