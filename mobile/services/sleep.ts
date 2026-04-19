import api from './api';

export interface SleepRecord {
  id: number;
  user_id: number;
  sleep_date: string;
  bedtime: string | null;
  wake_time: string | null;
  duration_hours: number | null;
  deep_sleep_hours: number | null;
  light_sleep_hours: number | null;
  rem_sleep_hours: number | null;
  awake_minutes: number | null;
  sleep_score: number | null;
  source: string;
  notes: string | null;
}

export interface SleepRecordCreate {
  sleep_date: string;
  bedtime?: string;
  wake_time?: string;
  duration_hours?: number;
  deep_sleep_hours?: number;
  light_sleep_hours?: number;
  rem_sleep_hours?: number;
  awake_minutes?: number;
  sleep_score?: number;
  source?: string;
  notes?: string;
}

export interface SleepDailyTrend {
  date: string;
  duration_hours: number | null;
  score: number | null;
  deep_pct: number | null;
}

export interface SleepStats {
  avg_duration: number | null;
  avg_score: number | null;
  avg_deep_pct: number | null;
  trend: SleepDailyTrend[];
}

export interface SleepDebt {
  current_debt_hours: number;
  recommended_hours: number;
  avg_actual_hours: number;
  days_analyzed: number;
}

export async function getSleepRecords(limit = 14): Promise<SleepRecord[]> {
  const { data } = await api.get<SleepRecord[]>('/sleep/records/me', { params: { limit } });
  return data;
}

export async function getSleepStats(days = 7): Promise<SleepStats> {
  const { data } = await api.get<SleepStats>('/sleep/stats/me', { params: { days } });
  return data;
}

export async function getDeepAnalysis(days = 7): Promise<{ analysis: string }> {
  const { data } = await api.get<{ analysis: string }>('/sleep/deep-analysis', { params: { days } });
  return data;
}

export async function getSleepDebt(days = 14): Promise<SleepDebt> {
  const { data } = await api.get<SleepDebt>('/sleep/debt', { params: { days } });
  return data;
}

export async function createSleepRecord(record: SleepRecordCreate): Promise<SleepRecord> {
  const { data } = await api.post<SleepRecord>('/sleep/records', record);
  return data;
}

export async function deleteSleepRecord(id: number): Promise<void> {
  await api.delete(`/sleep/records/${id}`);
}
