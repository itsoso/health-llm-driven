/**
 * 格式化工具函数
 */

/**
 * 格式化睡眠时长
 * @param seconds 秒数
 * @returns 格式化字符串，如 "7小时30分"
 */
export function formatSleepDuration(seconds?: number | null): string {
  if (!seconds) return '--';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours === 0) return `${minutes}分钟`;
  if (minutes === 0) return `${hours}小时`;
  return `${hours}小时${minutes}分`;
}

/**
 * 格式化运动时长
 * @param seconds 秒数
 * @returns 格式化字符串，如 "1:30:00" 或 "45:30"
 */
export function formatWorkoutDuration(seconds?: number | null): string {
  if (!seconds) return '--:--';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

/**
 * 格式化配速
 * @param secondsPerKm 每公里秒数
 * @returns 格式化字符串，如 "5'30\""
 */
export function formatPace(secondsPerKm?: number | null): string {
  if (!secondsPerKm) return '--';
  const minutes = Math.floor(secondsPerKm / 60);
  const seconds = Math.floor(secondsPerKm % 60);
  return `${minutes}'${seconds.toString().padStart(2, '0')}"`;
}

/**
 * 格式化距离
 * @param meters 米数
 * @returns 格式化字符串，如 "5.2 km" 或 "800 m"
 */
export function formatDistance(meters?: number | null): string {
  if (!meters) return '--';
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(2)} km`;
  }
  return `${Math.round(meters)} m`;
}

/**
 * 格式化日期
 * @param dateStr 日期字符串
 * @returns 格式化字符串，如 "2026年1月8日"
 */
export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '--';
  const date = new Date(dateStr);
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

/**
 * 格式化时间
 * @param timeStr 时间字符串
 * @returns 格式化字符串，如 "14:30"
 */
export function formatTime(timeStr?: string | null): string {
  if (!timeStr) return '--';
  return timeStr.substring(0, 5);
}

/**
 * 获取睡眠评分等级
 */
export function getSleepScoreLevel(score?: number | null): {
  label: string;
  color: string;
} {
  if (!score) return { label: '无数据', color: '#9ca3af' };
  if (score >= 85) return { label: '优秀', color: '#22c55e' };
  if (score >= 70) return { label: '良好', color: '#3b82f6' };
  if (score >= 50) return { label: '一般', color: '#f59e0b' };
  return { label: '较差', color: '#ef4444' };
}

/**
 * 获取压力等级
 */
export function getStressLevel(stress?: number | null): {
  label: string;
  color: string;
} {
  if (!stress) return { label: '无数据', color: '#9ca3af' };
  if (stress <= 25) return { label: '休息', color: '#3b82f6' };
  if (stress <= 50) return { label: '低', color: '#22c55e' };
  if (stress <= 75) return { label: '中', color: '#f59e0b' };
  return { label: '高', color: '#ef4444' };
}

