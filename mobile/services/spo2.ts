import api from './api';

export interface SpO2Point {
  timestamp: number;
  time: string;
  value: number;
}

export interface SpO2NightSummary {
  record_date: string;
  avg_spo2: number | null;
  min_spo2: number | null;
  max_spo2: number | null;
  below_90_count: number;
  desaturation_events: number;
  odi: number | null;
  data_points: number;
}

export interface SpO2NightlyData {
  record_date: string;
  summary: SpO2NightSummary;
  timeline: SpO2Point[];
  sleep_start: string | null;
  sleep_end: string | null;
}

export interface SpO2TrendData {
  days: number;
  daily_data: SpO2NightSummary[];
  avg_nightly_spo2: number | null;
  avg_odi: number | null;
  nights_with_odi_above_5: number;
}

export async function getSpO2Nightly(date: string): Promise<SpO2NightlyData> {
  const { data } = await api.get<SpO2NightlyData>(`/spo2/me/nightly/${date}`);
  return data;
}

export async function getSpO2Trend(days = 7): Promise<SpO2TrendData> {
  const { data } = await api.get<SpO2TrendData>('/spo2/me/trend', { params: { days } });
  return data;
}

export async function getSpO2LatestNight(): Promise<SpO2NightlyData | null> {
  try {
    const { data } = await api.get<SpO2NightlyData>('/spo2/me/latest-night');
    return data;
  } catch {
    return null;
  }
}
