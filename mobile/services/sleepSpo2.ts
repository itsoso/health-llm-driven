// SpO2 Nocturnal Analysis service (P1b backend)
// 调 /sleep/spo2/analysis 和 /sleep/spo2/insights

import api from './api';

export interface SpO2Event {
  start_ts: string;
  end_ts: string;
  duration_seconds: number;
  min_spo2: number;
  baseline_spo2: number | null;
  drop_magnitude: number;
  concurrent_hr_delta: number | null;
  concurrent_respiration_rate: number | null;
  sleep_stage: string | null;
}

export interface SpO2Correlation {
  category: string; // medication | supplement | exercise | diet | environment | diagnostic
  subject: string;
  rule: string;
  hypothesis: string;
  suggested_action: string;
  severity: 'alert' | 'warning' | 'info';
  confidence: 'high' | 'medium' | 'low';
  evidence: Record<string, any>;
}

export interface SpO2NightAnalysis {
  night_date: string;
  odi: number;
  events_count: number;
  min_spo2: number | null;
  avg_spo2: number | null;
  total_sleep_minutes: number;
  events: SpO2Event[];
  correlations: SpO2Correlation[];
  action_priorities: string[];
  ask_questions?: string[];
}

export interface SpO2BehaviorAB {
  behavior: string;
  with_count: number;
  without_count: number;
  odi_with: number;
  odi_without: number;
  delta: number;
  effect: '可能加重' | '可能改善' | '不显著';
}

export interface SpO2Insights {
  weeks: number;
  from_date: string;
  to_date: string;
  total_nights: number;
  avg_odi: number;
  ab_comparisons: SpO2BehaviorAB[];
}

export async function getNightAnalysis(nightDate: string): Promise<SpO2NightAnalysis> {
  const { data } = await api.get<SpO2NightAnalysis>('/sleep/spo2/analysis', {
    params: { night_date: nightDate },
  });
  return data;
}

export async function reanalyzeNight(nightDate: string): Promise<SpO2NightAnalysis> {
  const { data } = await api.post<SpO2NightAnalysis>('/sleep/spo2/reanalyze', null, {
    params: { night_date: nightDate },
  });
  return data;
}

export async function getInsights(weeks = 4): Promise<SpO2Insights> {
  const { data } = await api.get<SpO2Insights>('/sleep/spo2/insights', {
    params: { weeks },
  });
  return data;
}

// 夜间对齐时序（P1a API 复用）
export interface NightlyTimeseriesPoint {
  sample_time: string; // HH:MM:SS
  value: number | null;
  epoch_ms: number | null;
}

export interface NightlyTimeseriesResponse {
  record_date: string;
  metrics: Record<string, NightlyTimeseriesPoint[]>; // spo2 / hr / respiration / hrv / stress
  counts: Record<string, number>;
  sleep_stages: Array<{ start_ms: number; end_ms: number; level: string }>;
}

export async function getNightlyTimeseries(
  date: string,
  metrics = 'spo2,hr,respiration,sleep_stage',
): Promise<NightlyTimeseriesResponse> {
  const { data } = await api.get<NightlyTimeseriesResponse>(
    `/garmin/nightly/me/${date}`,
    { params: { metrics } },
  );
  return data;
}
