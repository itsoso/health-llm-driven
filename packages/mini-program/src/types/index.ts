/**
 * 小程序类型定义
 */

// 微信登录响应
export interface WechatLoginResponse {
  access_token?: string | null;  // 如果未审核，则为null
  token_type: string;
  user_id?: number;
  is_new_user?: boolean;
  nickname?: string;
  is_approved?: boolean;  // 是否已通过审核
  message?: string;  // 提示信息
}

// Garmin 数据
export interface GarminData {
  id: number;
  user_id: number;
  record_date: string;
  steps: number | null;
  resting_heart_rate: number | null;
  avg_heart_rate: number | null;
  hrv: number | null;
  hrv_status: string | null;
  sleep_score: number | null;
  total_sleep_duration: number | null;
  deep_sleep_duration: number | null;
  light_sleep_duration: number | null;
  rem_sleep_duration: number | null;
  awake_duration: number | null;
  stress_level: number | null;
  stress_avg?: number | null; // 兼容字段
  stress_max?: number | null; // 兼容字段
  stress_rest_duration?: number | null; // 兼容字段
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_most_charged: number | null;
  body_battery_lowest: number | null;
  body_battery_current: number | null;
  calories_total: number | null;
  active_calories: number | null;
  spo2_avg: number | null;
  spo2_min: number | null;
  spo2_max: number | null;
}

// 鼻炎记录
export interface RhinitisRecord {
  id?: number;
  user_id?: number;
  checkin_date: string;
  sneeze_count: number | null;
  sneeze_time: string | null;
  sneeze_times?: { time: string; count: number }[];
  nasal_wash_done: boolean;
  nasal_wash_time: string | null;
  nasal_wash_count?: number;
  nasal_wash_times?: { time: string; type: 'wash' | 'soak' }[];
  saline_soak_done: boolean;
  saline_soak_time: string | null;
  notes: string | null;
}

// 每日建议（1天建议）
export interface OneDayRecommendation {
  status: string;
  date: string;
  analysis_date?: string;
  user?: string;
  sleep_analysis?: string | null;
  activity_analysis?: string | null;
  heart_rate_analysis?: string | null;
  stress_analysis?: string | null;
  overall_status?: string;
  priority_recommendations?: string[];
  daily_goals?: string[];
  raw_data?: {
    sleep_score?: number | null;
    sleep_duration_minutes?: number | null;
    steps?: number | null;
    resting_heart_rate?: number | null;
    stress_avg?: number | null;
    body_battery_most_charged?: number | null;
  };
}

// 每日建议响应
export interface DailyRecommendation {
  status: string;
  date: string;
  analysis_date?: string;
  one_day?: OneDayRecommendation;
  seven_day?: any;
  cached?: boolean;
}

// 运动记录摘要
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

// 饮食记录
export interface DietRecord {
  id: number;
  record_date: string;
  meal_type: string;
  food_items: string;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
}

// 饮水记录
export interface WaterRecord {
  id: number;
  user_id: number;
  record_date: string;
  drink_time: string;
  amount: number;
  drink_type: string;
  notes: string | null;
}

// 饮水统计
export interface WaterStats {
  total_days: number;
  avg_daily_amount: number;
  total_amount: number;
  max_daily_amount: number;
  days_meeting_goal: number;
}

// 饮水日汇总
export interface WaterDailySummary {
  date: string;
  total_amount: number;
  goal_amount: number;
  records: WaterRecord[];
  completion_rate: number;
}

// 体重记录
export interface WeightRecord {
  id: number;
  user_id: number;
  record_date: string;
  weight: number;
  body_fat_percentage: number | null;
  muscle_mass: number | null;
  notes: string | null;
}

// 体重统计
export interface WeightStats {
  current_weight: number | null;
  initial_weight: number | null;
  lowest_weight: number | null;
  highest_weight: number | null;
  weight_change: number | null;
  avg_weight: number | null;
  total_records: number;
}

// 每日饮食汇总
export interface DailyDietSummary {
  record_date: string;
  total_calories: number;
  total_protein: number;
  total_carbs: number;
  total_fat: number;
  total_fiber: number;
  meals_count: number;
  meals: DietRecord[];
}

// 运动前指导
export interface PreWorkoutGuidance {
  user_status: {
    body_battery: number | null;
    hrv: number | null;
    sleep_score: number | null;
    stress_level: number | null;
    readiness: string;
  };
  training_objective: string;
  heart_rate_zones: {
    max_heart_rate: number;
    zone2_fat_burn: [number, number];
    zone3_aerobic: [number, number];
    zone4_threshold: [number, number];
  };
  warm_up: string[];
  key_reminders: string[];
  course_insights: string[];
}

// API 端点
export const API_ENDPOINTS = {
  AUTH: {
    WECHAT_LOGIN: '/wechat/login',
  },
  GARMIN: {
    MY_DATA: '/daily-health/garmin/me',
  },
  RECOMMENDATION: {
    TODAY: '/daily-recommendation/me',
  },
  CHECKIN: {
    TODAY: '/checkin/me/today',
    CREATE: '/checkin/me',
  },
  WORKOUT: {
    MY_LIST: '/workout/me',
    PRE_GUIDANCE: '/workout/pre-workout-guidance',
  },
  DIET: {
    MY_DAILY: '/diet/records/me/date',
  },
  WATER: {
    QUICK_ADD: '/water/records/quick',
    MY_RECORDS: '/water/records/me',
    MY_DATE: '/water/records/me/date',
    MY_STATS: '/water/records/me/stats',
  },
  WEIGHT: {
    CREATE: '/weight/records',
    MY_RECORDS: '/weight/records/me',
    MY_STATS: '/weight/records/me/stats',
  },
  NEWS: {
    LIST: '/news/articles',
    DETAIL: '/news/articles',
  },
  USER_API_KEY: {
    LIST: '/user-api-keys',
    CREATE: '/user-api-keys',
    DELETE: '/user-api-keys',
  },
  EXTERNAL_RECOMMENDATIONS: {
    LIST: '/external-recommendations',
    TODAY: '/external-recommendations/today',
  },
};

// 工具函数
export function formatSleepDuration(minutes: number | null): string {
  if (minutes === null || minutes === undefined) return '--';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}小时${mins}分钟`;
}

export function getSleepScoreLevel(score: number | null): { level: string; color: string } {
  if (score === null || score === undefined) {
    return { level: '未知', color: '#9CA3AF' };
  }
  if (score >= 80) return { level: '优秀', color: '#10B981' };
  if (score >= 60) return { level: '良好', color: '#3B82F6' };
  if (score >= 40) return { level: '一般', color: '#F59E0B' };
  return { level: '较差', color: '#EF4444' };
}

export function getStressLevel(stress: number | null | undefined): { level: string; color: string } {
  if (stress === null || stress === undefined) {
    return { level: '未知', color: '#9CA3AF' };
  }
  if (stress <= 25) return { level: '放松', color: '#10B981' };
  if (stress <= 50) return { level: '正常', color: '#3B82F6' };
  if (stress <= 75) return { level: '中等', color: '#F59E0B' };
  return { level: '高压', color: '#EF4444' };
}

// 获取血氧饱和度状态
export function getSpO2Level(spo2: number | null | undefined): { level: string; color: string } {
  if (spo2 === null || spo2 === undefined) {
    return { level: '未知', color: '#9CA3AF' };
  }
  if (spo2 >= 95) return { level: '正常', color: '#10B981' };
  if (spo2 >= 90) return { level: '偏低', color: '#F59E0B' };
  return { level: '异常', color: '#EF4444' };
}

// ========== AI 调度器类型 ==========

// 简报区块
export interface BriefingSection {
  title: string;
  status: 'good' | 'warning' | 'poor' | 'info';
  items: string[];
}

// 早间简报
export interface MorningBriefing {
  date: string;
  greeting: string;
  sections: BriefingSection[];
}

// 实时建议
export interface AIRecommendation {
  timestamp: string;
  primary: {
    icon: string;
    title: string;
    message: string;
    checkin_action?: string; // 可打卡事项类型：water, nasal_wash, supplement, exercise, weight, diet
  } | null;
  secondary: Array<string | {
    text: string;
    checkin_action?: string; // 可打卡事项类型
  }>;
  status: Record<string, any>;
}

// 健康提醒
export interface HealthReminder {
  type: string;
  title: string;
  message: string;
  scheduled_time: string;
  priority: number;
}

// 日程项
export interface ScheduleItem {
  time: string;
  activity: string;
  category: string;
  duration_minutes: number;
  tasks: string[];
}

// ========== 用户 API Key 相关类型 ==========

// 用户 API Key
export interface UserApiKey {
  id: number;
  name: string;
  api_key: string | null;  // 只在创建时返回
  scopes: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

// 创建 API Key 请求
export interface ApiKeyCreateRequest {
  name: string;
  scopes?: string;
}

// 外部建议
export interface ExternalRecommendation {
  id: number;
  category: string;  // exercise, diet, sleep, supplement, general
  title: string;
  content: string;
  source_name: string;
  recommendation_date: string;
  created_at: string;
}

// 今日外部建议响应（按类别分组）
export interface TodayExternalRecommendations {
  date: string;
  has_recommendations: boolean;
  categories: Record<string, ExternalRecommendation[]>;
}
