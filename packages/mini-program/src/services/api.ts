/**
 * API 服务
 */
import Taro from '@tarojs/taro';
import { get, post, put, del, postNoAuth, setToken } from './request';
import {
  API_ENDPOINTS,
  WechatLoginResponse,
  GarminData,
  RhinitisRecord,
  DailyRecommendation,
  WorkoutSummary,
  DailyDietSummary,
  PreWorkoutGuidance,
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
 * 获取运动前指导
 * @param workoutType 运动类型（如：running, cycling等）
 * @param goalId 可选的目标ID
 */
export async function getPreWorkoutGuidance(workoutType: string, goalId?: number): Promise<PreWorkoutGuidance | null> {
  try {
    return await post<PreWorkoutGuidance>(API_ENDPOINTS.WORKOUT.PRE_GUIDANCE, {
      workout_type: workoutType,
      goal_id: goalId,
    });
  } catch (e) {
    console.error('获取运动指导失败:', e);
    return null;
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

// ========== 饮水记录 API ==========

import type { WaterRecord, WaterStats, WaterDailySummary, WeightRecord, WeightStats } from '../types';

/**
 * 快速添加饮水记录
 * @param amount 饮水量（毫升），默认250ml
 */
export async function quickAddWater(amount: number = 250): Promise<{
  id: number;
  amount: number;
  drink_type: string;
  record_date: string;
  drink_time: string;
}> {
  return await post(`${API_ENDPOINTS.WATER.QUICK_ADD}?amount=${amount}`, {});
}

/**
 * 获取某日饮水记录
 */
export async function getWaterRecordsByDate(date: string): Promise<WaterDailySummary> {
  return await get(`${API_ENDPOINTS.WATER.MY_DATE}/${date}`);
}

/**
 * 获取饮水统计
 */
export async function getWaterStats(days: number = 7): Promise<WaterStats> {
  return await get(`${API_ENDPOINTS.WATER.MY_STATS}?days=${days}`);
}

/**
 * 获取最近饮水记录
 */
export async function getWaterRecords(limit: number = 50): Promise<WaterRecord[]> {
  return await get(`${API_ENDPOINTS.WATER.MY_RECORDS}?limit=${limit}`);
}

// ========== 体重记录 API ==========

/**
 * 创建体重记录
 */
export async function createWeightRecord(data: {
  weight: number;
  body_fat_percentage?: number | null;
  muscle_mass?: number | null;
  notes?: string | null;
}): Promise<WeightRecord> {
  const today = getBeijingToday();
  return await post(API_ENDPOINTS.WEIGHT.CREATE, {
    record_date: today,
    ...data,
  });
}

/**
 * 获取体重记录列表
 */
export async function getWeightRecords(limit: number = 90): Promise<WeightRecord[]> {
  return await get(`${API_ENDPOINTS.WEIGHT.MY_RECORDS}?limit=${limit}`);
}

/**
 * 获取体重统计
 */
export async function getWeightStats(days: number = 30): Promise<WeightStats> {
  return await get(`${API_ENDPOINTS.WEIGHT.MY_STATS}?days=${days}`);
}

// ========== 资讯 API ==========

export interface NewsArticle {
  id: number;
  source_batch_id: string;
  source_type: string;
  title: string;
  summary: string | null;
  content?: string;
  tags: string[] | null;
  topics?: string[] | null;
  key_people?: string[] | null;
  source_group: string | null;
  llm_models?: string[] | null;
  aggregator_model?: string | null;
  is_pinned: boolean;
  view_count: number;
  created_at: string;
}

/**
 * 获取资讯列表
 */
export async function getNewsList(page: number = 1, pageSize: number = 20, sourceType?: string): Promise<NewsArticle[]> {
  let url = `${API_ENDPOINTS.NEWS.LIST}?page=${page}&page_size=${pageSize}`;
  if (sourceType) {
    url += `&source_type=${sourceType}`;
  }
  return await get(url);
}

/**
 * 获取资讯详情
 */
export async function getNewsDetail(articleId: number): Promise<NewsArticle> {
  return await get(`${API_ENDPOINTS.NEWS.DETAIL}/${articleId}`);
}

/**
 * 推送 LLM 分析结果到资讯
 */
export async function pushToNews(data: {
  source_batch_id: string;
  title: string;
  content: string;
  summary?: string;
  source_type?: string;
  tags?: string[];
  llm_models?: string[];
  aggregator_model?: string;
  visibility: string;
}): Promise<any> {
  return await post(API_ENDPOINTS.NEWS.PUSH, data);
}

// ========== 用户 API Key 管理 ==========

import type { UserApiKey, ApiKeyCreateRequest, ExternalRecommendation, TodayExternalRecommendations } from '../types';

/**
 * 获取用户的 API Key 列表
 */
export async function getUserApiKeys(): Promise<UserApiKey[]> {
  return await get(API_ENDPOINTS.USER_API_KEY.LIST);
}

/**
 * 创建新的 API Key
 */
export async function createUserApiKey(data: ApiKeyCreateRequest): Promise<UserApiKey> {
  return await post(API_ENDPOINTS.USER_API_KEY.CREATE, data);
}

/**
 * 删除 API Key
 */
export async function deleteUserApiKey(keyId: number): Promise<{ ok: boolean; message: string }> {
  return await del(`${API_ENDPOINTS.USER_API_KEY.DELETE}/${keyId}`);
}

// ========== 外部建议 ==========

/**
 * 获取外部建议列表
 */
export async function getExternalRecommendations(
  date?: string,
  category?: string,
  limit: number = 20
): Promise<ExternalRecommendation[]> {
  let url = `${API_ENDPOINTS.EXTERNAL_RECOMMENDATIONS.LIST}?limit=${limit}`;
  if (date) {
    url += `&date=${date}`;
  }
  if (category) {
    url += `&category=${category}`;
  }
  return await get(url);
}

/**
 * 获取今日外部建议（按类别分组）
 */
export async function getTodayExternalRecommendations(): Promise<TodayExternalRecommendations> {
  return await get(API_ENDPOINTS.EXTERNAL_RECOMMENDATIONS.TODAY);
}

// ===== OpenClaw AI 对话 =====

export async function chatSend(message: string, conversationId?: number, mode?: string): Promise<any> {
  return await post(API_ENDPOINTS.CHAT.SEND, {
    message,
    conversation_id: conversationId || undefined,
    ...(mode ? { mode } : {}),
  });
}

export async function getChatConversations(limit: number = 20): Promise<any[]> {
  return await get(`${API_ENDPOINTS.CHAT.CONVERSATIONS}?limit=${limit}`);
}

export async function getChatMessages(conversationId: number): Promise<any> {
  return await get(`${API_ENDPOINTS.CHAT.CONVERSATIONS}/${conversationId}`);
}

export async function deleteChatConversation(conversationId: number): Promise<void> {
  return await del(`${API_ENDPOINTS.CHAT.CONVERSATIONS}/${conversationId}`);
}

export async function chatTranscribe(audioBase64: string, audioFormat: string = 'mp3'): Promise<{ text: string }> {
  return await post(API_ENDPOINTS.CHAT.TRANSCRIBE, { audio_base64: audioBase64, audio_format: audioFormat });
}

export async function recognizeFood(imageBase64: string, imageType: string = 'image/jpeg'): Promise<{ success: boolean; foods: any[]; meal_description: string; health_tips: string; totals: any }> {
  return await post(API_ENDPOINTS.DIET_AI.RECOGNIZE, { image_base64: imageBase64, image_type: imageType });
}

// ===== OpenClaw API =====

export async function openclawSend(message: string, conversationId?: number, imageBase64?: string, imageType?: string): Promise<{ reply: string; conversation_id: number; message_id: number }> {
  return await post(API_ENDPOINTS.OPENCLAW.SEND, {
    message,
    conversation_id: conversationId || undefined,
    image_base64: imageBase64 || undefined,
    image_type: imageType || undefined,
  });
}

export async function openclawGetConversations(limit: number = 20): Promise<any[]> {
  return await get(`${API_ENDPOINTS.OPENCLAW.CONVERSATIONS}?limit=${limit}`);
}

export async function openclawGetConversation(conversationId: number): Promise<any> {
  return await get(`${API_ENDPOINTS.OPENCLAW.CONVERSATIONS}/${conversationId}`);
}

export async function openclawDeleteConversation(conversationId: number): Promise<void> {
  return await del(`${API_ENDPOINTS.OPENCLAW.CONVERSATIONS}/${conversationId}`);
}

export async function openclawRateMessage(messageId: number, rating: 1 | -1): Promise<{ ok: boolean }> {
  return await post(`${API_ENDPOINTS.OPENCLAW.RATE}/${messageId}/rate`, { rating });
}

export async function getQuickQuestions(limit: number = 6): Promise<{ id: number; question: string }[]> {
  try {
    return await get(`${API_ENDPOINTS.OPENCLAW.QUICK_QUESTIONS}?limit=${limit}`);
  } catch (e) {
    console.error('获取快捷问题失败:', e);
    return [];
  }
}

// ===== 情绪追踪 =====

import type { MoodRecord, MoodStats } from '../types';

/**
 * 创建情绪记录
 */
export async function createMoodRecord(data: {
  record_date: string;
  mood_score: number;
  mood_tags?: string[];
  energy_level?: number;
  stress_level?: number;
  anxiety_level?: number;
  sleep_quality?: number;
  journal?: string;
  triggers?: string[];
  coping_methods?: string[];
}): Promise<MoodRecord> {
  return await post(API_ENDPOINTS.MOOD.CREATE, data);
}

/**
 * 获取情绪记录列表
 */
export async function getMoodRecords(
  startDate?: string,
  endDate?: string,
  limit: number = 30,
): Promise<MoodRecord[]> {
  let url = `${API_ENDPOINTS.MOOD.MY_RECORDS}?limit=${limit}`;
  if (startDate) url += `&start_date=${startDate}`;
  if (endDate) url += `&end_date=${endDate}`;
  return await get(url);
}

/**
 * 获取今日情绪记录
 */
export async function getTodayMoodRecord(): Promise<MoodRecord | null> {
  return await get(API_ENDPOINTS.MOOD.TODAY);
}

/**
 * 更新情绪记录
 */
export async function updateMoodRecord(
  recordId: number,
  data: Partial<{
    mood_score: number;
    mood_tags: string[];
    energy_level: number;
    stress_level: number;
    anxiety_level: number;
    sleep_quality: number;
    journal: string;
    triggers: string[];
    coping_methods: string[];
  }>,
): Promise<MoodRecord> {
  return await put(`${API_ENDPOINTS.MOOD.CREATE}/${recordId}`, data);
}

/**
 * 删除情绪记录
 */
export async function deleteMoodRecord(recordId: number): Promise<void> {
  return await del(`${API_ENDPOINTS.MOOD.CREATE}/${recordId}`);
}

/**
 * 获取情绪统计
 */
export async function getMoodStats(days: number = 7): Promise<MoodStats> {
  return await get(`${API_ENDPOINTS.MOOD.STATS}?days=${days}`);
}

// ===== 健康报告 =====

export interface HealthReportItem {
  id: number;
  report_type: string;
  start_date: string;
  end_date: string;
  title: string;
  exercise_summary: Record<string, any>;
  diet_summary: Record<string, any>;
  sleep_summary: Record<string, any>;
  weight_summary: Record<string, any>;
  mood_summary: Record<string, any>;
  vital_signs_summary: Record<string, any>;
  ai_recommendations: string[];
  health_score: number | null;
  comparison: Record<string, any>;
  created_at: string;
}

/**
 * 生成健康报告
 */
export async function generateHealthReport(reportType: string): Promise<HealthReportItem> {
  return await post(API_ENDPOINTS.HEALTH_REPORT.GENERATE, { report_type: reportType });
}

/**
 * 获取报告列表
 */
export async function getHealthReports(limit: number = 20): Promise<HealthReportItem[]> {
  return await get(`${API_ENDPOINTS.HEALTH_REPORT.LIST}?limit=${limit}`);
}

/**
 * 获取报告详情
 */
export async function getHealthReportDetail(reportId: number): Promise<HealthReportItem> {
  return await get(`${API_ENDPOINTS.HEALTH_REPORT.DETAIL}/${reportId}`);
}

// ===== 身体成分分析 =====

import type { BodyCompositionTrend, BodyAnalysisResult } from '../types';

/**
 * 获取身体成分趋势
 */
export async function getBodyCompositionTrend(days: number = 30): Promise<BodyCompositionTrend> {
  return await get(`${API_ENDPOINTS.BODY_COMPOSITION.TREND}?days=${days}`);
}

/**
 * 获取身体成分分析
 */
export async function getBodyAnalysis(): Promise<BodyAnalysisResult> {
  return await get(API_ENDPOINTS.BODY_COMPOSITION.ANALYSIS);
}

// ===== 健康评分 =====

import type { HealthScoreResult, HealthScoreTrend } from '../types';

/**
 * 获取每日健康评分
 */
export async function getDailyHealthScore(targetDate?: string): Promise<HealthScoreResult> {
  let url = API_ENDPOINTS.HEALTH_SCORE.DAILY;
  if (targetDate) url += `?target_date=${targetDate}`;
  return await get(url);
}

/**
 * 获取健康评分趋势
 */
export async function getHealthScoreTrend(days: number = 7): Promise<HealthScoreTrend> {
  return await get(`${API_ENDPOINTS.HEALTH_SCORE.TREND}?days=${days}`);
}

// ===== 用药管理 =====

import type { MedicationItem, MedicationTodayStatus } from '../types';

export async function addMedication(data: {
  name: string; dosage?: string; frequency?: string;
  times_per_day?: number; reminder_times?: string[]; notes?: string;
}): Promise<MedicationItem> {
  return await post(API_ENDPOINTS.MEDICATION.ADD, data);
}

export async function getMyMedications(activeOnly: boolean = true): Promise<MedicationItem[]> {
  return await get(`${API_ENDPOINTS.MEDICATION.MY_LIST}?active_only=${activeOnly}`);
}

export async function logMedication(data: {
  medication_id: number; taken_time: string; status: string;
  skip_reason?: string;
}): Promise<any> {
  return await post(API_ENDPOINTS.MEDICATION.LOG, data);
}

export async function getTodayMedicationStatus(): Promise<MedicationTodayStatus[]> {
  return await get(API_ENDPOINTS.MEDICATION.TODAY);
}

export async function getMedicationAdherence(days: number = 7): Promise<any> {
  return await get(`${API_ENDPOINTS.MEDICATION.ADHERENCE}?days=${days}`);
}

// ===== 女性健康 =====

import type { MenstrualCycleItem, CyclePrediction, CycleStats, CycleCalendar, CycleSymptomItem } from '../types';

export async function startPeriod(start_date: string, flow_intensity: string = 'moderate'): Promise<MenstrualCycleItem> {
  return await post(API_ENDPOINTS.WOMENS_HEALTH.START_PERIOD, { start_date, flow_intensity });
}

export async function endPeriod(cycleId: number, end_date: string): Promise<MenstrualCycleItem> {
  return await post(`${API_ENDPOINTS.WOMENS_HEALTH.END_PERIOD}/${cycleId}/end`, { end_date });
}

export async function getMyCycles(limit: number = 12): Promise<MenstrualCycleItem[]> {
  return await get(`${API_ENDPOINTS.WOMENS_HEALTH.CYCLES}?limit=${limit}`);
}

export async function predictNextPeriod(): Promise<{ prediction: CyclePrediction | null; message?: string }> {
  return await get(API_ENDPOINTS.WOMENS_HEALTH.PREDICT);
}

export async function logCycleSymptom(data: {
  record_date: string; symptom_type: string; severity: number; notes?: string;
}): Promise<CycleSymptomItem> {
  return await post(API_ENDPOINTS.WOMENS_HEALTH.SYMPTOMS, data);
}

export async function getCycleStats(): Promise<CycleStats> {
  return await get(API_ENDPOINTS.WOMENS_HEALTH.STATS);
}

export async function getCycleCalendar(year: number, month: number): Promise<CycleCalendar> {
  return await get(`${API_ENDPOINTS.WOMENS_HEALTH.CALENDAR}?year=${year}&month=${month}`);
}

export async function getMyCycleSymptoms(params?: {
  cycle_id?: number; start_date?: string; end_date?: string;
}): Promise<CycleSymptomItem[]> {
  const query = new URLSearchParams();
  if (params?.cycle_id) query.append('cycle_id', String(params.cycle_id));
  if (params?.start_date) query.append('start_date', params.start_date);
  if (params?.end_date) query.append('end_date', params.end_date);
  const qs = query.toString();
  return await get(`${API_ENDPOINTS.WOMENS_HEALTH.MY_SYMPTOMS}${qs ? '?' + qs : ''}`);
}
