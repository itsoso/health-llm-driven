/**
 * API 服务
 */
import Taro from '@tarojs/taro';
import { get, post, put, postNoAuth, setToken } from './request';
import { 
  API_ENDPOINTS,
  WechatLoginResponse, 
  GarminData, 
  RhinitisRecord,
  DailyRecommendation,
  WorkoutSummary,
  DailyDietSummary,
} from '../types';

/**
 * 微信登录
 * @param nickname 可选的用户昵称
 * @param inviteCode 邀请码（新用户注册时必需）
 */
export async function wechatLogin(nickname?: string, inviteCode?: string): Promise<WechatLoginResponse> {
  // 1. 调用 wx.login 获取 code
  const loginResult = await Taro.login();
  
  if (!loginResult.code) {
    throw new Error('微信登录失败');
  }

  // 2. 发送 code 到后端换取 token（登录不需要认证）
  const response = await postNoAuth<WechatLoginResponse>(API_ENDPOINTS.AUTH.WECHAT_LOGIN, {
    code: loginResult.code,
    nickname: nickname || undefined,
    invite_code: inviteCode || undefined,
  });

  // 3. 保存 token 和用户名（仅当已审核时）
  if (response.access_token) {
    setToken(response.access_token);
  }
  if (response.nickname) {
    Taro.setStorageSync('user_name', response.nickname);
  }

  return response;
}

/**
 * 更新用户昵称
 */
export async function updateUserName(name: string): Promise<{ success: boolean; name: string }> {
  const response = await post<{ success: boolean; name: string }>('/users/me/name', { name });
  if (response.success) {
    Taro.setStorageSync('user_name', response.name);
  }
  return response;
}

/**
 * 获取 Garmin 数据
 */
export async function getGarminData(
  startDate: string,
  endDate: string
): Promise<GarminData[]> {
  // 确保日期格式正确（YYYY-MM-DD）
  const normalizedStartDate = startDate.split('T')[0];
  const normalizedEndDate = endDate.split('T')[0];
  
  return get<GarminData[]>(API_ENDPOINTS.GARMIN.MY_DATA, {
    start_date: normalizedStartDate,
    end_date: normalizedEndDate,
  });
}

/**
 * 获取北京时间的今日日期 (YYYY-MM-DD)
 */
function getBeijingToday(): string {
  const now = new Date();
  // 使用 UTC 时间加上 8 小时得到北京时间
  const utcTime = now.getTime() + now.getTimezoneOffset() * 60 * 1000;
  const beijingTime = new Date(utcTime + 8 * 60 * 60 * 1000);
  
  const year = beijingTime.getFullYear();
  const month = String(beijingTime.getMonth() + 1).padStart(2, '0');
  const day = String(beijingTime.getDate()).padStart(2, '0');
  
  return `${year}-${month}-${day}`;
}

/**
 * 获取今日 Garmin 数据（使用北京时间）
 */
export async function getTodayGarminData(): Promise<GarminData | null> {
  const today = getBeijingToday();
  console.log('[API] 获取今日 Garmin 数据, 日期:', today);
  
  const data = await getGarminData(today, today);
  console.log('[API] 获取到的数据:', data.length > 0 ? `steps=${data[0].steps}, battery=${data[0].body_battery_most_charged}` : '无数据');
  return data.length > 0 ? data[0] : null;
}

/**
 * 获取今日建议
 */
export async function getDailyRecommendation(): Promise<DailyRecommendation> {
  return get<DailyRecommendation>(API_ENDPOINTS.RECOMMENDATION.TODAY);
}

/**
 * 鼻炎追踪 - 获取今日记录
 */
export async function getTodayRhinitis(): Promise<RhinitisRecord | null> {
  try {
    return await get<RhinitisRecord>(API_ENDPOINTS.CHECKIN.TODAY);
  } catch (e) {
    return null;
  }
}

/**
 * 鼻炎追踪 - 保存记录
 */
export async function saveRhinitisRecord(
  data: Partial<RhinitisRecord>
): Promise<RhinitisRecord> {
  const today = new Date().toISOString().split('T')[0];
  return post<RhinitisRecord>(API_ENDPOINTS.CHECKIN.CREATE, {
    checkin_date: today,
    ...data,
  });
}

/**
 * 检查是否绑定了 Garmin
 */
export async function checkGarminBinding(userId: number): Promise<{
  has_garmin: boolean;
  garmin_email?: string;
  sync_enabled: boolean;
  credentials_valid: boolean;
}> {
  return get(`/wechat/check-binding/${userId}`);
}

/**
 * 同步当前用户的 Garmin 数据（使用已保存的凭据）
 */
export async function syncMyGarminData(days: number = 1): Promise<{
  status: string;
  message: string;
  success_count?: number;
  error_count?: number;
  activities_count?: number;
}> {
  return post(`/data-collection/garmin/me/sync?days=${days}`, {});
}

/**
 * 获取今日运动记录
 */
export async function getTodayWorkouts(): Promise<WorkoutSummary[]> {
  try {
    return await get<WorkoutSummary[]>(API_ENDPOINTS.WORKOUT.MY_LIST, { days: 1 });
  } catch (e) {
    console.error('获取运动记录失败:', e);
    return [];
  }
}

/**
 * 获取今日饮食汇总
 */
export async function getTodayDietSummary(): Promise<DailyDietSummary | null> {
  try {
    const today = getBeijingToday();
    return await get<DailyDietSummary>(`${API_ENDPOINTS.DIET.MY_DAILY}/${today}`);
  } catch (e) {
    console.error('获取饮食汇总失败:', e);
    return null;
  }
}

// ========== AI 调度器 API ==========

import { 
  MorningBriefing, 
  AIRecommendation, 
  HealthReminder, 
  ScheduleItem 
} from '../types';

/**
 * 获取早间健康简报
 */
export async function getMorningBriefing(): Promise<MorningBriefing | null> {
  try {
    return await get<MorningBriefing>('/ai-scheduler/morning-briefing');
  } catch (e) {
    console.error('获取早间简报失败:', e);
    return null;
  }
}

/**
 * 获取实时健康建议
 */
export async function getAIRecommendation(): Promise<AIRecommendation | null> {
  try {
    return await get<AIRecommendation>('/ai-scheduler/recommendation');
  } catch (e) {
    console.error('获取实时建议失败:', e);
    return null;
  }
}

/**
 * 获取当前时段提醒
 */
export async function getCurrentReminders(): Promise<{ reminders: HealthReminder[]; current_time: string }> {
  try {
    return await get<{ reminders: HealthReminder[]; current_time: string }>('/ai-scheduler/reminders');
  } catch (e) {
    console.error('获取当前提醒失败:', e);
    return { reminders: [], current_time: '' };
  }
}

/**
 * 获取今日日程安排
 */
export async function getDailySchedule(): Promise<{ schedule: ScheduleItem[]; generated_at: string }> {
  try {
    return await get<{ schedule: ScheduleItem[]; generated_at: string }>('/ai-scheduler/daily-schedule');
  } catch (e) {
    console.error('获取日程安排失败:', e);
    return { schedule: [], generated_at: '' };
  }
}

/**
 * 获取综合健康摘要
 */
export async function getAISummary(): Promise<{
  briefing: MorningBriefing;
  recommendation: AIRecommendation;
  reminders: HealthReminder[];
  generated_at: string;
} | null> {
  try {
    return await get('/ai-scheduler/summary');
  } catch (e) {
    console.error('获取健康摘要失败:', e);
    return null;
  }
}

// ========== 每日复盘 API ==========

/**
 * 获取今日复盘
 */
export async function getTodayReview(): Promise<any> {
  return await get('/review/daily/today');
}

/**
 * 获取指定日期复盘
 */
export async function getDailyReview(date: string): Promise<any> {
  return await get(`/review/daily/${date}`);
}

/**
 * 更新每日复盘
 */
export async function updateDailyReview(date: string, data: any): Promise<any> {
  return await put(`/review/daily/${date}`, data);
}

/**
 * 刷新复盘健康数据
 */
export async function refreshDailyReview(date: string): Promise<any> {
  return await post(`/review/daily/${date}/refresh`, {});
}

/**
 * 获取复盘列表
 */
export async function getReviewList(limit: number = 30): Promise<any[]> {
  return await get(`/review/daily?limit=${limit}`);
}

/**
 * 获取本周复盘
 */
export async function getCurrentWeekReview(): Promise<any> {
  return await get('/review/period/week/current');
}

/**
 * 获取本月复盘
 */
export async function getCurrentMonthReview(): Promise<any> {
  return await get('/review/period/month/current');
}

/**
 * 获取复盘连续天数
 */
export async function getReviewStreak(): Promise<{ current_streak: number; total_reviews: number; last_30_days: number }> {
  return await get('/review/stats/streak');
}

/**
 * AI 生成复盘总结
 */
export async function generateAIReviewSummary(date: string, period: string): Promise<{ ai_summary: string } | null> {
  try {
    return await post(`/review/ai-summary`, { date, period });
  } catch (e) {
    console.error('AI生成总结失败:', e);
    return null;
  }
}
