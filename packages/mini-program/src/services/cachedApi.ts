/**
 * 带缓存的 API 服务
 * 自动处理缓存逻辑，减少不必要的网络请求
 */

import { localCache, CacheConfig, getCacheKey } from '../utils/cache';
import * as api from './api';
import type {
  GarminData,
  DailyRecommendation,
  RhinitisRecord,
  WorkoutSummary,
  DailyDietSummary,
  MorningBriefing,
  AIRecommendation,
  HealthReminder,
  ScheduleItem,
  PreWorkoutGuidance
} from '../types';

/**
 * 获取今日 Garmin 数据（带缓存）
 */
export async function getTodayGarminDataCached(forceRefresh = false): Promise<GarminData | null> {
  const cacheKey = getCacheKey('garmin_today');
  
  return localCache.withCache(
    cacheKey,
    () => api.getTodayGarminData(),
    CacheConfig.GARMIN_DATA,
    forceRefresh
  );
}

/**
 * 获取每日推荐（带缓存）
 */
export async function getDailyRecommendationCached(forceRefresh = false): Promise<DailyRecommendation> {
  const cacheKey = getCacheKey('daily_recommendation');
  
  return localCache.withCache(
    cacheKey,
    () => api.getDailyRecommendation(),
    CacheConfig.DAILY_RECOMMENDATION,
    forceRefresh
  );
}

/**
 * 获取今日鼻炎记录（带缓存）
 */
export async function getTodayRhinitisCached(forceRefresh = false): Promise<RhinitisRecord | null> {
  const cacheKey = getCacheKey('rhinitis_today');
  
  return localCache.withCache(
    cacheKey,
    () => api.getTodayRhinitis(),
    CacheConfig.RHINITIS_RECORD,
    forceRefresh
  );
}

/**
 * 获取今日运动记录（带缓存）
 */
export async function getTodayWorkoutsCached(forceRefresh = false): Promise<WorkoutSummary[]> {
  const cacheKey = getCacheKey('workouts_today');
  
  return localCache.withCache(
    cacheKey,
    () => api.getTodayWorkouts(),
    CacheConfig.WORKOUT_RECORDS,
    forceRefresh
  );
}

/**
 * 获取今日饮食摘要（带缓存）
 */
export async function getTodayDietSummaryCached(forceRefresh = false): Promise<DailyDietSummary | null> {
  const cacheKey = getCacheKey('diet_summary_today');
  
  return localCache.withCache(
    cacheKey,
    () => api.getTodayDietSummary(),
    CacheConfig.DIET_SUMMARY,
    forceRefresh
  );
}

/**
 * 获取早间简报（带缓存）
 */
export async function getMorningBriefingCached(forceRefresh = false): Promise<MorningBriefing> {
  const cacheKey = getCacheKey('morning_briefing');
  
  return localCache.withCache(
    cacheKey,
    () => api.getMorningBriefing(),
    CacheConfig.MORNING_BRIEFING,
    forceRefresh
  );
}

/**
 * 获取 AI 推荐（带缓存）
 */
export async function getAIRecommendationCached(forceRefresh = false): Promise<AIRecommendation> {
  const cacheKey = getCacheKey('ai_recommendation');
  
  return localCache.withCache(
    cacheKey,
    () => api.getAIRecommendation(),
    CacheConfig.AI_RECOMMENDATION,
    forceRefresh
  );
}

/**
 * 获取当前提醒（带缓存）
 */
export async function getCurrentRemindersCached(forceRefresh = false): Promise<{ reminders: HealthReminder[] }> {
  const cacheKey = 'current_reminders'; // 提醒不需要日期，因为是实时的
  
  return localCache.withCache(
    cacheKey,
    () => api.getCurrentReminders(),
    CacheConfig.CURRENT_REMINDERS,
    forceRefresh
  );
}

/**
 * 获取每日日程（带缓存）
 */
export async function getDailyScheduleCached(forceRefresh = false): Promise<{ schedule: ScheduleItem[] }> {
  const cacheKey = getCacheKey('daily_schedule');
  
  return localCache.withCache(
    cacheKey,
    () => api.getDailySchedule(),
    CacheConfig.DAILY_SCHEDULE,
    forceRefresh
  );
}

/**
 * 获取运动指导（带缓存）
 */
export async function getPreWorkoutGuidanceCached(
  workoutType: string,
  forceRefresh = false
): Promise<PreWorkoutGuidance> {
  const cacheKey = `workout_guidance_${workoutType}`;
  
  return localCache.withCache(
    cacheKey,
    () => api.getPreWorkoutGuidance(workoutType),
    CacheConfig.WORKOUT_GUIDANCE,
    forceRefresh
  );
}

/**
 * 清除运动指导缓存
 */
export function clearWorkoutGuidanceCache(workoutType?: string): void {
  if (workoutType) {
    localCache.remove(`workout_guidance_${workoutType}`);
    console.log(`[缓存] 已清除${workoutType}运动指导缓存`);
  } else {
    // 清除所有运动类型的缓存
    const types = ['running', 'cycling', 'swimming', 'strength', 'yoga'];
    types.forEach(type => localCache.remove(`workout_guidance_${type}`));
    console.log('[缓存] 已清除所有运动指导缓存');
  }
}

/**
 * 清除所有首页相关缓存
 * 用于手动刷新或数据更新后
 */
export function clearHomePageCache(): void {
  const today = getCacheKey('', new Date()).split('_')[1]; // 获取今天的日期部分

  const cacheKeys = [
    getCacheKey('garmin_today'),
    getCacheKey('daily_recommendation'),
    getCacheKey('rhinitis_today'),
    getCacheKey('workouts_today'),
    getCacheKey('diet_summary_today'),
    getCacheKey('morning_briefing'),
    getCacheKey('ai_recommendation'),
    'current_reminders',
    getCacheKey('daily_schedule'),
  ];

  cacheKeys.forEach(key => localCache.remove(key));
  // 同时清除运动指导缓存
  clearWorkoutGuidanceCache();
  console.log('[缓存] 已清除首页缓存');
}

/**
 * 获取缓存统计信息
 */
export function getCacheStats() {
  return localCache.getStats();
}
