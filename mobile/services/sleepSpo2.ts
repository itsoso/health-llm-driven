// SpO2 Nocturnal Analysis service (P1b backend)
// 调 /sleep/spo2/analysis 和 /sleep/spo2/insights

import api from './api';
import type { ActionCardCreateInput } from './actionCards';

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

export interface SpO2SnoreEvent {
  start_ts: string;
  end_ts: string;
  intensity?: 'low' | 'medium' | 'high';
  confidence?: number;
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
  snore_events?: SpO2SnoreEvent[];
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

export async function confirmNoAlcohol(nightDate: string): Promise<{ ok: boolean; created: boolean; id: number }> {
  const { data } = await api.post('/sleep/spo2/confirm-no-alcohol', null, {
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

export function buildSleepExperimentCardPayload(action: string, nightDate: string): ActionCardCreateInput {
  const trimmed = action.trim();
  return {
    title: `睡眠实验：${trimmed}`.slice(0, 80),
    content: [
      '## 睡眠呼吸实验',
      '',
      `- 参考夜晚：${nightDate}`,
      `- 今晚尝试：${trimmed}`,
      '- 明天复盘：对比 ODI、最低 SpO2、氧降事件数和主观睡眠感受。',
    ].join('\n'),
    card_type: 'plan',
    source_type: 'sleep_spo2',
    source_id: nightDate,
    priority: 2,
  };
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

// ---------------------------------------------------------------------------
// Longitudinal (H2-6): 近 N 天夜间 SpO2 事件聚合 + OSAHS pattern
// ---------------------------------------------------------------------------

export type NightSeverity = 'normal' | 'mild' | 'moderate' | 'severe' | 'unknown';

export interface NightSummary {
  night_date: string;
  events_count: number;
  odi: number | null;
  min_spo2: number | null;
  avg_drop_magnitude: number | null;
  total_sleep_minutes: number | null;
  events_rem_pct: number | null;
  severity: NightSeverity;
}

export type PatternFlag =
  | 'frequent_desaturation'
  | 'notable_hypoxia'
  | 'rem_predominant'
  | 'severe_nights_present';

export interface LongitudinalPattern {
  covered_nights: number;
  nights_with_odi: number;
  avg_odi: number | null;
  median_min_spo2: number | null;
  pct_nights_odi_ge_5: number | null;
  pct_nights_min_spo2_below_90: number | null;
  pct_events_in_rem: number | null;
  mild_nights: number;
  moderate_nights: number;
  severe_nights: number;
  pattern_flags: PatternFlag[];
}

export interface LongitudinalResponse {
  window: { start: string; end: string; days: number };
  nights: NightSummary[];
  pattern: LongitudinalPattern;
}

export async function getSpo2Longitudinal(days = 30): Promise<LongitudinalResponse> {
  const { data } = await api.get<LongitudinalResponse>(
    '/sleep/spo2/longitudinal', { params: { days } },
  );
  return data;
}

export const SEVERITY_LABEL: Record<NightSeverity, string> = {
  normal: '正常',
  mild: '轻度',
  moderate: '中度',
  severe: '重度',
  unknown: '—',
};

export const SEVERITY_COLOR: Record<NightSeverity, string> = {
  normal: '#34C759',
  mild: '#FFCC00',
  moderate: '#FF9500',
  severe: '#FF3B30',
  unknown: '#8E8E93',
};

export const FLAG_LABEL: Record<PatternFlag, { label: string; hint: string }> = {
  frequent_desaturation: {
    label: '频繁氧降',
    hint: '近半数夜 ODI ≥ 5，建议医生进一步评估',
  },
  notable_hypoxia: {
    label: '显著低氧',
    hint: '≥ 25% 夜最低 SpO2 低于 90%',
  },
  rem_predominant: {
    label: 'REM 期为主',
    hint: '事件集中在 REM 睡眠，是典型 OSAHS 模式',
  },
  severe_nights_present: {
    label: '存在重度夜',
    hint: '已出现 ≥3 夜 ODI ≥ 30',
  },
};
