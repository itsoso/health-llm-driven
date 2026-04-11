/**
 * Personal Outcome API client
 *
 * 长期健康改善档案：时间序列 + 干预事件 + 摘要。
 */
import api from './client';

export type OutcomeRange = '6m' | '1y' | '2y' | 'all';
export type OutcomeGranularity = 'week' | 'month';

export interface TimelinePoint {
  bucket: string;
  date: string;
  hrv: number | null;
  rhr: number | null;
  sleep_score: number | null;
  deep_sleep_min: number | null;
  body_battery_high: number | null;
  steps: number | null;
  weight_kg: number | null;
  systolic: number | null;
  diastolic: number | null;
  samples: number;
}

export interface TimelineEvent {
  id: string;
  kind: 'supplement_start' | 'medical_exam' | 'first_bp' | 'milestone';
  date: string;
  title: string;
  detail: string | null;
  color: string | null;
}

export interface OutcomeMetric {
  first: number | null;
  last: number | null;
  delta: number | null;
  unit: string;
  desirable: 'up' | 'down' | 'flat';
}

export interface OutcomeSummary {
  total_days: number;
  covered_days: number;
  metrics: {
    hrv: OutcomeMetric;
    rhr: OutcomeMetric;
    weight: OutcomeMetric;
    sleep_score: OutcomeMetric;
  };
}

export interface OutcomeTimelineResponse {
  range: OutcomeRange;
  granularity: OutcomeGranularity;
  start_date: string | null;
  end_date: string;
  points: TimelinePoint[];
  events: TimelineEvent[];
  summary: OutcomeSummary;
}

export interface EventWindowStats {
  hrv: number | null;
  rhr: number | null;
  sleep_score: number | null;
  deep_sleep_min: number | null;
  steps: number | null;
  samples: number;
}

export interface EventImpactResponse {
  event_id: string;
  title: string;
  detail: string | null;
  event_date: string;
  window_days: number;
  before: EventWindowStats;
  after: EventWindowStats;
}

export async function getMyOutcomeTimeline(
  range: OutcomeRange = '2y',
  granularity: OutcomeGranularity = 'month'
): Promise<OutcomeTimelineResponse> {
  const { data } = await api.get('/personal-outcome/me/timeline', {
    params: { range, granularity },
  });
  return data;
}

export async function getMyEventImpact(
  eventId: string,
  windowDays = 30
): Promise<EventImpactResponse> {
  const { data } = await api.get(
    `/personal-outcome/me/events/${encodeURIComponent(eventId)}/impact`,
    { params: { window_days: windowDays } }
  );
  return data;
}
