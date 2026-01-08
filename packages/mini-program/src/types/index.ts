/**
 * 小程序类型定义
 */

// 微信登录响应
export interface WechatLoginResponse {
  access_token: string;
  token_type: string;
  user_id?: number;
  is_new_user?: boolean;
  nickname?: string;
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
  stress_avg: number | null;
  stress_max: number | null;
  stress_rest_duration: number | null;
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_most_charged: number | null;
  body_battery_lowest: number | null;
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

// 每日建议
export interface DailyRecommendation {
  date: string;
  status: string;
  recommendations: {
    category: string;
    content: string;
    priority: string;
  }[];
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

export function getStressLevel(stress: number | null): { level: string; color: string } {
  if (stress === null || stress === undefined) {
    return { level: '未知', color: '#9CA3AF' };
  }
  if (stress <= 25) return { level: '放松', color: '#10B981' };
  if (stress <= 50) return { level: '正常', color: '#3B82F6' };
  if (stress <= 75) return { level: '中等', color: '#F59E0B' };
  return { level: '高压', color: '#EF4444' };
}
