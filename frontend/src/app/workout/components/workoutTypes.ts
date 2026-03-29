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
  workouts_by_type: Record<string, { count: number; duration_minutes: number }>;
  recent_trend: string;
}

export interface LapData {
  lap: number;
  distance?: number;
  duration?: number;
  avg_hr?: number;
  max_hr?: number;
  avg_pace?: number;
  avg_speed?: number;
  elevation_gain?: number;
  elevation_loss?: number;
  calories?: number;
  avg_cadence?: number;
  avg_power?: number;
}

export interface WorkoutDetail {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  moving_duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  min_heart_rate: number | null;
  calories: number | null;
  active_calories: number | null;
  avg_pace_seconds_per_km: number | null;
  best_pace_seconds_per_km: number | null;
  avg_speed_kmh: number | null;
  max_speed_kmh: number | null;
  training_effect_aerobic: number | null;
  training_effect_anaerobic: number | null;
  training_load: number | null;
  vo2max: number | null;
  hr_zone_1_seconds: number | null;
  hr_zone_2_seconds: number | null;
  hr_zone_3_seconds: number | null;
  hr_zone_4_seconds: number | null;
  hr_zone_5_seconds: number | null;
  elevation_gain_meters: number | null;
  elevation_loss_meters: number | null;
  min_elevation_meters: number | null;
  max_elevation_meters: number | null;
  steps: number | null;
  avg_cadence: number | null;
  max_cadence: number | null;
  ai_analysis: string | null;
  heart_rate_data: string | null;
  pace_data: string | null;
  elevation_data: string | null;
  lap_data: string | null;
  source: string;
  external_id: string | null;
  start_time: string | null;
  end_time: string | null;
  route_data?: string | null;
}
