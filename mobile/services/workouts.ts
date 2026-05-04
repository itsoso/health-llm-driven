import api from './api';

export interface WorkoutSummary {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  calories: number | null;
  feeling: string | null;
  has_ai_analysis: boolean;
}

export interface WorkoutStats {
  total_workouts: number;
  total_duration_minutes: number;
  total_distance_km: number;
  total_calories: number;
  avg_duration_minutes: number;
  avg_distance_km: number;
  workouts_by_type: Record<string, number>;
  recent_trend: string;
}

export interface WorkoutDetail {
  id: number;
  user_id: number;
  source: string;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  calories: number | null;
  steps: number | null;
  avg_speed_kmh: number | null;
  max_speed_kmh: number | null;
  avg_pace_seconds_per_km: number | null;
  avg_cadence: number | null;
  max_cadence: number | null;
  avg_stride_length_cm: number | null;
  elevation_gain_meters: number | null;
  elevation_loss_meters: number | null;
  training_effect_aerobic: number | null;
  training_effect_anaerobic: number | null;
  vo2max: number | null;
  training_load: number | null;
  ai_analysis: string | null;
  post_workout_analysis: string | null;
  route_data: string | null;
}

export interface WorkoutAnalysis {
  workout_id: number;
  overall_rating: string;
  intensity_assessment: string;
  heart_rate_analysis: string | null;
  hr_zone_assessment: string | null;
  pace_analysis: string | null;
  training_effect_summary: string | null;
  recovery_recommendation: string;
  next_workout_suggestion: string;
  comparison_with_history: string | null;
  key_insights: string[];
  improvement_tips: string[];
}

export interface HeartRatePoint { time: number; hr: number; }
export interface PacePoint { time: number; pace: number; }
export interface ElevationPoint { distance: number; elevation: number; }

export interface HrZoneBucket { zone: string; minutes: number; percentage: number; }

export interface WorkoutChartData {
  workout_id?: number;
  workout_type?: string;
  duration_seconds?: number;
  heart_rate_timeline: HeartRatePoint[] | null;
  heart_rate_zones: HrZoneBucket[];
  pace_timeline?: PacePoint[] | null;
  elevation_timeline?: ElevationPoint[] | null;
  avg_heart_rate?: number | null;
  max_heart_rate?: number | null;
  avg_pace_display?: string | null;
  total_distance_km?: number | null;
  calories?: number | null;
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

export interface PostWorkoutAnalysisResponse {
  success: boolean;
  from_cache?: boolean;
  has_cache?: boolean;
  [key: string]: unknown;
}

export async function getPostWorkoutAnalysis(
  id: number,
  forceRegenerate = false,
  cacheOnly = false,
): Promise<PostWorkoutAnalysisResponse> {
  const { data } = await api.post<PostWorkoutAnalysisResponse>(
    `/workout/post-workout-analysis/${id}`,
    null,
    { params: { force_regenerate: forceRegenerate, cache_only: cacheOnly } },
  );
  return data;
}
