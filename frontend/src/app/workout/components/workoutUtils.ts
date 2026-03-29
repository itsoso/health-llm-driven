export const WORKOUT_TYPES: Record<string, { name: string; icon: string; color: string }> = {
  running: { name: '跑步', icon: '🏃', color: '#ef4444' },
  cycling: { name: '骑行', icon: '🚴', color: '#3b82f6' },
  swimming: { name: '游泳', icon: '🏊', color: '#06b6d4' },
  hiit: { name: 'HIIT', icon: '🔥', color: '#f97316' },
  cardio: { name: '有氧', icon: '❤️', color: '#ec4899' },
  strength: { name: '力量', icon: '💪', color: '#8b5cf6' },
  yoga: { name: '瑜伽/冥想', icon: '🧘', color: '#10b981' },
  walking: { name: '步行', icon: '🚶', color: '#84cc16' },
  hiking: { name: '登山/徒步', icon: '⛰️', color: '#a855f7' },
  other: { name: '其他', icon: '🏅', color: '#6b7280' },
};

export const HR_ZONE_COLORS = ['#94a3b8', '#22c55e', '#eab308', '#f97316', '#ef4444'];

export function formatDuration(seconds: number | null): string {
  if (!seconds) return '--:--';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function formatPace(secondsPerKm: number | null): string {
  if (!secondsPerKm) return '--\'--"';
  const mins = Math.floor(secondsPerKm / 60);
  const secs = secondsPerKm % 60;
  return `${mins}'${secs.toString().padStart(2, '0')}"`;
}

export function formatDistance(meters: number | null): string {
  if (!meters) return '--';
  return (meters / 1000).toFixed(2);
}
