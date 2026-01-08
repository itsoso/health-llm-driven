/**
 * 健康数据相关类型定义
 */

export interface GarminData {
  id: number;
  user_id: number;
  record_date: string;
  
  // 睡眠数据
  sleep_score?: number;
  total_sleep_duration?: number;
  deep_sleep_duration?: number;
  light_sleep_duration?: number;
  rem_sleep_duration?: number;
  awake_duration?: number;
  
  // 心率数据
  resting_heart_rate?: number;
  avg_heart_rate?: number;
  max_heart_rate?: number;
  min_heart_rate?: number;
  hrv?: number;
  hrv_status?: string;
  
  // 活动数据
  steps?: number;
  calories_burned?: number;
  active_calories?: number;
  active_minutes?: number;
  distance_meters?: number;
  floors_climbed?: number;
  
  // 压力和身体电量
  stress_level?: number;
  body_battery_most_charged?: number;
  body_battery_lowest?: number;
  
  // 血氧
  spo2_avg?: number;
  spo2_min?: number;
  spo2_max?: number;
  
  // VO2 Max
  vo2max_running?: number;
  vo2max_cycling?: number;
}

export interface RhinitisRecord {
  id?: number;
  checkin_date: string;
  sneeze_count?: number;
  sneeze_times?: Array<{ time: string; count: number }>;
  nasal_wash_count?: number;
  nasal_wash_times?: Array<{ time: string; type: string }>;
  notes?: string;
}

export interface DailyRecommendation {
  status: string;
  analysis_date: string;
  sleep_analysis: {
    status: string;
    score?: number;
    duration_hours?: number;
    message: string;
    suggestions: string[];
  };
  activity_analysis: {
    status: string;
    steps?: number;
    active_minutes?: number;
    message: string;
    suggestions: string[];
  };
  heart_rate_analysis: {
    status: string;
    resting_hr?: number;
    hrv?: number;
    message: string;
    suggestions: string[];
  };
  stress_analysis: {
    status: string;
    stress_level?: number;
    body_battery?: number;
    message: string;
    suggestions: string[];
  };
  overall_summary: string;
  priority_recommendations: string[];
  daily_goals: Array<{
    category: string;
    goal: string;
    target?: number;
    unit?: string;
  }>;
}

export interface HeartRateData {
  date: string;
  data: Array<{
    time: string;
    heart_rate: number;
  }>;
  summary: {
    avg: number;
    min: number;
    max: number;
    resting: number;
  };
}

