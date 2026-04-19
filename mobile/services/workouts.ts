import api from './api';

export interface WorkoutSummary {
  id: number;
  user_id: number;
  activity_type: string;
  start_time: string;
  duration_minutes: number;
  calories: number | null;
  distance_km: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  source: string;
  notes: string | null;
}

export interface WorkoutStats {
  total_workouts: number;
  total_duration_minutes: number;
  total_calories: number;
  avg_duration_minutes: number;
  avg_heart_rate: number | null;
  activity_breakdown: Record<string, number>;
  weekly_frequency: number;
}

export interface WorkoutDetail extends WorkoutSummary {
  avg_speed: number | null;
  training_effect_aerobic: number | null;
  training_effect_anaerobic: number | null;
  vo2max: number | null;
  steps: number | null;
}

export interface WorkoutAnalysis {
  summary: string;
  intensity_assessment: string;
  recovery_suggestion: string;
  improvement_tips: string[];
}

export interface WorkoutChartData {
  heart_rate_zones: { zone: string; minutes: number; percentage: number }[];
  heart_rate_timeline: { time: string; value: number }[];
}

export async function getWorkouts(limit = 20, offset = 0): Promise<WorkoutSummary[]> {
  const { data } = await api.get<WorkoutSummary[]>('/workout/me', { params: { limit, offset } });
  return data;
}

export async function getWorkoutStats(days = 30): Promise<WorkoutStats> {
  const { data } = await api.get<WorkoutStats>('/workout/me/stats', { params: { days } });
  return data;
}

export async function getWorkoutDetail(id: number): Promise<WorkoutDetail> {
  const { data } = await api.get<WorkoutDetail>(`/workout/me/${id}`);
  return data;
}

export async function getWorkoutChart(id: number): Promise<WorkoutChartData> {
  const { data } = await api.get<WorkoutChartData>(`/workout/me/${id}/chart`);
  return data;
}

export async function syncGarminWorkouts(): Promise<{ synced: number }> {
  const { data } = await api.post<{ synced: number }>('/workout/me/sync-garmin');
  return data;
}

export async function analyzeWorkout(id: number): Promise<WorkoutAnalysis> {
  const { data } = await api.post<WorkoutAnalysis>(`/workout/me/${id}/analyze`);
  return data;
}
