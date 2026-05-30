import api from './api';

export interface CheckinStreak {
  current_streak: number;
  best_streak: number;
}

/**
 * 读取打卡连续天数 (后端 /checkin/stats 真实计算, 见 backend/app/api/checkin.py).
 * 只取 streak 两个字段 —— 首页 StreakBadge 用. 失败由调用方 (React Query) 决定如何降级,
 * 这里不吞错、不假装 0.
 */
export async function getCheckinStreak(): Promise<CheckinStreak> {
  const { data } = await api.get('/checkin/stats');
  return {
    current_streak: data?.current_streak ?? 0,
    best_streak: data?.best_streak ?? 0,
  };
}
