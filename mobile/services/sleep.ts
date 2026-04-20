import api from './api';

export interface SleepRecord {
  id: number;
  user_id: number;
  record_date: string;
  bedtime: string;
  wake_time: string;
  sleep_quality: number;
  total_duration_minutes: number | null;
  wake_count: number | null;
  had_dream: boolean | null;
  dream_description: string | null;
  fall_asleep_difficulty: number | null;
  morning_feeling: number | null;
  notes: string | null;
  created_at: string;
}

export interface SleepRecordCreate {
  record_date: string;
  bedtime: string;
  wake_time: string;
  sleep_quality: number;
  wake_count?: number;
  had_dream?: boolean;
  dream_description?: string;
  fall_asleep_difficulty?: number;
  morning_feeling?: number;
  notes?: string;
}

export interface GarminSleepDay {
  record_date: string;
  sleep_score: number | null;
  total_sleep_duration: number | null;
  deep_sleep_duration: number | null;
  rem_sleep_duration: number | null;
  light_sleep_duration: number | null;
  awake_duration: number | null;
  sleep_start_time: string | null;
  sleep_end_time: string | null;
}

export interface SleepDailyTrend {
  date: string;
  duration_hours: number | null;
  score: number | null;
}

export interface SleepStats {
  avg_duration_hours: number | null;
  avg_sleep_score: number | null;
  avg_deep_pct: number | null;
  daily_trend: SleepDailyTrend[];
}

export interface SleepDebt {
  status: string;
  days_analyzed: number;
  target_hours: number;
  cumulative_debt_hours: number;
  avg_daily_deficit_hours: number;
  debt_severity: string;
  recovery_plan: string;
}

export async function getGarminSleepData(days = 7): Promise<GarminSleepDay[]> {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const { data } = await api.get<GarminSleepDay[]>('/daily-health/garmin/me', {
    params: { start_date: fmt(start), end_date: fmt(end) },
  });
  return data;
}

export function computeSleepStats(data: GarminSleepDay[]): SleepStats {
  const withSleep = data.filter(d => d.total_sleep_duration != null && d.total_sleep_duration > 0);
  const durations = withSleep.map(d => (d.total_sleep_duration ?? 0) / 60);
  const scores = withSleep.filter(d => d.sleep_score != null).map(d => d.sleep_score!);
  const deepPcts = withSleep
    .filter(d => d.deep_sleep_duration != null && d.total_sleep_duration)
    .map(d => (d.deep_sleep_duration! / d.total_sleep_duration!) * 100);

  return {
    avg_duration_hours: durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : null,
    avg_sleep_score: scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    avg_deep_pct: deepPcts.length > 0 ? deepPcts.reduce((a, b) => a + b, 0) / deepPcts.length : null,
    daily_trend: data.map(d => ({
      date: d.record_date,
      duration_hours: d.total_sleep_duration != null ? d.total_sleep_duration / 60 : null,
      score: d.sleep_score,
    })),
  };
}

export async function getDeepAnalysis(days = 7): Promise<{ analysis: string }> {
  const { data } = await api.get<any>('/sleep/deep-analysis', { params: { days } });
  return { analysis: data.analysis || data.summary || JSON.stringify(data) };
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
